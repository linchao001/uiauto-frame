"""Pytest plugin: browser session, config, flow injection, failure artifacts."""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from pilot.core.artifacts import ArtifactCollector
from pilot.core.browser import (
    BrowserSession,
    SharedBrowser,
    finalize_trace,
    launch_browser,
    launch_extra_browser,
    launch_isolated_session,
    open_page,
)
from pilot.core.config import PilotConfig, load_config
from pilot.core.device_filter import deselect_for_env
from pilot.core.priority_filter import (
    deselect_for_priority,
    marker_priority,
    parse_priority_cli,
)
from pilot.core.failure_capture import (
    bind_failure_capture,
    clear_failure_capture,
    was_assertion_screenshot_taken,
)
from pilot.core.logging import (
    LOG_FORMAT,
    configure_logging,
    enable_pytest_logging,
    get_logger,
)
from pilot.core.report_attach import attach_failure_artifacts
from pilot.db.client import DbClient
from pilot.db.session import bind_db, clear_db
from pilot.flow.base import BaseFlow
from pilot.notify.feishu import SessionSummary, notify_session_summary
from pilot.report.archive import (
    DEFAULT_REPORT_ROOT,
    artifacts_root_for,
    finalize_report_archive,
    prepare_html_report,
    report_run_dir,
)
from pilot.report.from_report import (
    FromReportError,
    deselect_not_in_report,
    extract_failed_nodeids,
    unmatched_wanted,
)
from pilot.report.capture import bind_test_item, reset_test_item
from pilot.report.case_marks import (
    register_case_markers,
    resolve_case_meta,
    user_properties_for_meta,
)
from pilot.report.html_utils import (
    pop_html_extras,
    pop_steps,
    render_case_detail_html,
    render_title_cell_html,
)
from pilot.ssh.client import SshClient
from pilot.ssh.session import bind_ssh, clear_ssh

# 插件被 pytest 加载时即标记，避免后续 get_logger 在 import 阶段挂 stdout handler
enable_pytest_logging()

logger = get_logger("pilot")

_DEFAULT_LOG_CLI_LEVEL = "INFO"
_DEFAULT_LOG_REPORT_LEVEL = "INFO"
# sessionstart 记录墙钟，供 sessionfinish 汇总耗时
_SESSION_START_ATTR = "_pilot_session_start"


def pytest_addhooks(pluginmanager: pytest.PytestPluginManager) -> None:
    """注册产品可实现的报告元数据钩子。"""
    from pilot import hookspecs

    pluginmanager.add_hookspecs(hookspecs)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("pilot")
    group.addoption(
        "--pilot-config",
        action="store",
        default=None,
        help=(
            "Pilot config file or directory "
            "(file: legacy env.yaml; dir: product.yaml + env/*.yaml). "
            "Default: config/ under test root"
        ),
    )
    group.addoption(
        "--pilot-env",
        "--env",
        action="store",
        default=None,
        dest="pilot_env",
        help=(
            "Target environment / device name "
            "(matches config/env/<name>.yaml or named block in legacy env.yaml)"
        ),
    )
    group.addoption(
        "--pilot-browser",
        action="store",
        default=None,
        dest="pilot_browser",
        help="Browser engine: chromium | firefox | webkit (overrides config; for CI matrix jobs)",
    )
    group.addoption(
        "--pilot-headed",
        action="store_true",
        default=False,
        help="Run browser headed (overrides config headless)",
    )
    group.addoption(
        "--no-live-log",
        action="store_true",
        dest="pilot_no_live_log",
        default=False,
        help="Disable Pilot default live terminal logging (pytest log_cli at INFO)",
    )
    group.addoption(
        "--priority",
        action="store",
        default=None,
        dest="pilot_priority",
        help=(
            "Run only cases marked @pytest.mark.P0|P1|P2|P3 "
            "(comma-separated levels). Unmarked cases are deselected."
        ),
    )
    group.addoption(
        "--report",
        action="store_true",
        dest="pilot_report",
        default=False,
        help=(
            "Write a self-contained HTML report under "
            "reports/<env>/<timestamp>/ (requires pytest-html)"
        ),
    )
    group.addoption(
        "--report-dir",
        action="store",
        dest="pilot_report_dir",
        default=DEFAULT_REPORT_ROOT,
        help=f"Root directory for archived HTML reports (default: {DEFAULT_REPORT_ROOT})",
    )
    group.addoption(
        "--from-report",
        action="store",
        dest="pilot_from_report",
        default=None,
        metavar="PATH",
        help=(
            "Re-run only Failed/Error cases from a pytest-html report.html "
            "(or a run directory containing report.html)"
        ),
    )


def _configure_pytest_logging_defaults(config: pytest.Config) -> None:
    """终端实时日志 + 报告 Captured log；不向 stdout 重复挂 handler。

    用户 CLI / ini 优先于框架默认。
    """
    if not getattr(config.option, "pilot_no_live_log", False):
        if config.getoption("log_cli_level") is None and not config.getini("log_cli"):
            config.option.log_cli_level = _DEFAULT_LOG_CLI_LEVEL
        if config.getoption("log_cli_format") is None and not config.getini("log_cli_format"):
            config.option.log_cli_format = LOG_FORMAT

    if config.getoption("log_level") is None and not config.getini("log_level"):
        config.option.log_level = _DEFAULT_LOG_REPORT_LEVEL


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    enable_pytest_logging()
    configure_logging()
    # 须在 pytest LoggingPlugin（trylast）读取 option 之前设置默认
    _configure_pytest_logging_defaults(config)
    config.addinivalue_line(
        "markers",
        "device(*names): run only when --env/--pilot-env matches one of the given device names",
    )
    for level, desc in (
        ("P0", "highest priority"),
        ("P1", "high priority"),
        ("P2", "medium priority"),
        ("P3", "low priority"),
    ):
        config.addinivalue_line(
            "markers",
            f"{level}: {desc} case (filter via -m {level} or --priority {level})",
        )
    register_case_markers(config)
    if getattr(config.option, "pilot_report", False) and not hasattr(
        config.option, "htmlpath"
    ):
        logger.warning(
            "--report requested but pytest-html is not installed; "
            "reinstall with: pip install -e ."
        )
        return
    env = _resolve_active_env(config)
    path = prepare_html_report(config, env=env)
    if path is not None:
        # 报告里的「打开 Trace」依赖本机协议；开测时注册，避免只在失败时才写注册表
        from pilot.report.trace_protocol import ensure_trace_protocol

        ensure_trace_protocol()
        logger.info("html report -> %s", path)


def _layered_config_dir(base: Path) -> Path | None:
    """``base/config`` 为分层配置根（product.yaml 或 env/）时返回该目录。"""
    layered = base / "config"
    if (layered / "product.yaml").is_file() or (layered / "env").is_dir():
        return layered
    return None


def _discover_layered_config(start: Path) -> Path | None:
    """从 ``start`` 向上查找分层 ``config/`` 目录。"""
    try:
        cur = start.resolve()
    except OSError:
        return None
    for base in (cur, *cur.parents):
        found = _layered_config_dir(base)
        if found is not None:
            return found
    return None


def _discover_legacy_config(start: Path) -> Path | None:
    """从 ``start`` 向上查找单文件 ``config/env.yaml``。"""
    try:
        cur = start.resolve()
    except OSError:
        return None
    for base in (cur, *cur.parents):
        legacy = base / "config" / "env.yaml"
        if legacy.is_file():
            return legacy
    return None


def _path_from_nodeid_arg(arg: str) -> Path:
    """pytest 参数（路径或 nodeid）→ 本地 Path。"""
    raw = str(arg).split("::", 1)[0]
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _config_search_starts(config: pytest.Config) -> list[Path]:
    """配置发现起点：用例参数、cwd、启动目录、rootpath。"""
    starts: list[Path] = []
    for arg in config.args:
        path = _path_from_nodeid_arg(arg)
        starts.append(path if path.is_dir() or not path.suffix else path.parent)
        starts.append(path.parent)
    starts.append(Path.cwd())
    inv = getattr(config, "invocation_params", None)
    if inv is not None:
        starts.append(Path(str(inv.dir)))
    starts.append(Path(str(config.rootpath)))
    return starts


def _resolve_config_path(config: pytest.Config) -> Path | None:
    """解析配置路径：CLI > 分层 config/ > 单文件 config/env.yaml。

    除 ``rootpath`` 外，从用例路径、cwd、pytest 启动目录向上查找，避免 monorepo 根
    的 ``pyproject.toml`` 抢 rootpath 时读不到产品仓 ``config/``。
    """
    cli = config.getoption("--pilot-config")
    if cli:
        return Path(cli)

    seen: set[Path] = set()
    for raw in _config_search_starts(config):
        try:
            start = raw.resolve()
        except OSError:
            continue
        if start in seen:
            continue
        seen.add(start)
        layered = _discover_layered_config(start)
        if layered is not None:
            return layered

    seen_legacy: set[Path] = set()
    for raw in _config_search_starts(config):
        try:
            start = raw.resolve()
        except OSError:
            continue
        if start in seen_legacy:
            continue
        seen_legacy.add(start)
        legacy = _discover_legacy_config(start)
        if legacy is not None:
            return legacy
    return None


def _load_pilot_config(
    pytestconfig: pytest.Config,
    *,
    explicit_config_path: Path | str | None = None,
) -> PilotConfig:
    """按 CLI 加载并应用 headed / browser 覆盖。

    ``explicit_config_path`` 供产品 conftest 钉死本仓 ``config/``。
    """
    if explicit_config_path is not None:
        path = Path(explicit_config_path)
    else:
        path = _resolve_config_path(pytestconfig)
    env = pytestconfig.getoption("pilot_env")
    cfg = load_config(path, env=env)
    if pytestconfig.getoption("--pilot-headed"):
        cfg.browser.headless = False
    browser = pytestconfig.getoption("pilot_browser")
    if browser:
        cfg.browser.browser = str(browser)
    return cfg


def _resolve_active_env(config: pytest.Config) -> str | None:
    """解析当前设备/env 名，供 device marker 过滤。"""
    try:
        return _load_pilot_config(config).env
    except Exception as exc:
        logger.debug("could not resolve env: %s", exc)
        explicit = config.getoption("pilot_env", default=None)
        return str(explicit) if explicit else None


@pytest.fixture(scope="session")
def pilot_config(pytestconfig: pytest.Config) -> PilotConfig:
    return _load_pilot_config(pytestconfig)


@pytest.fixture(scope="session", autouse=True)
def pilot_ssh_session(
    pilot_config: PilotConfig,
) -> Generator[SshClient | None, None, None]:
    """Session SSH：已配置则绑定客户端（懒连接）；未配则为 None。"""
    if not pilot_config.ssh.enabled:
        bind_ssh(None)
        yield None
        return
    client = SshClient(pilot_config.ssh)
    bind_ssh(client)
    try:
        yield client
    finally:
        clear_ssh()


@pytest.fixture(scope="session")
def ssh(pilot_ssh_session: SshClient | None) -> SshClient:
    """用例用 SSH 客户端；未在 YAML 配置 ``ssh`` 时明确报错。"""
    if pilot_ssh_session is None:
        raise pytest.UsageError(
            "SSH is not configured. Add an ``ssh`` block (at least user) "
            "to env YAML, e.g.\n\n"
            "  ssh:\n"
            "    user: sshuser\n"
            "    password: changeme\n"
        )
    return pilot_ssh_session


@pytest.fixture(scope="session")
def db(
    pilot_config: PilotConfig,
    pilot_ssh_session: SshClient | None,
) -> Generator[DbClient, None, None]:
    """Session 级 DbClient；未在 YAML 配置 ``db`` 时明确报错。

    若同时配了 ``ssh`` 且 ``auto_setup_remote``，首次连库失败会尝试远程开通。
    """
    if not pilot_config.db.enabled:
        raise pytest.UsageError(
            "DB is not configured. Add a ``db`` block (user and/or database) "
            "to env YAML, e.g.\n\n"
            "  db:\n"
            "    user: root\n"
            "    password: secret\n"
            "    database: app\n"
        )
    client = DbClient(pilot_config.db, ssh=pilot_ssh_session)
    bind_db(client)
    try:
        client.connect()
        yield client
    finally:
        clear_db()


@pytest.fixture(scope="session")
def auth_provider(pytestconfig: pytest.Config):
    """产品鉴权实现；未 ``register_auth_provider`` 时为 UnsetAuthProvider。"""
    from pilot.account.auth import get_auth_provider

    return get_auth_provider(pytestconfig)


@pytest.fixture(scope="session", autouse=True)
def pilot_recreate_test_account(
    request: pytest.FixtureRequest,
    pilot_config: PilotConfig,
    auth_provider,
) -> None:
    """会话开始调用 ``AuthProvider.recreate_test_account``（默认 no-op）。

    若配置启用了 db，则注入 ``db`` fixture；否则传 ``None``。
    """
    db = None
    if pilot_config.db.enabled:
        db = request.getfixturevalue("db")
    auth_provider.recreate_test_account(pilot_config, db)


@pytest.fixture
def artifacts(request: pytest.FixtureRequest) -> ArtifactCollector | None:
    """截图/trace 目录：仅 ``--report`` 时落在本次 report 目录下的 artifacts/。"""
    root = artifacts_root_for(request.config)
    if root is None:
        return None
    return ArtifactCollector(
        root / request.node.name,
        report_dir=report_run_dir(request.config),
    )


@pytest.fixture(scope="session")
def pilot_browser(pilot_config: PilotConfig) -> Generator[SharedBrowser, None, None]:
    """整场（每 worker）共用一个浏览器进程，避免每条用例冷启动 Chromium。"""
    shared = launch_browser(pilot_config.browser)
    try:
        yield shared
    finally:
        shared.close()


class _PilotPageRuntime:
    """单条用例的主 Page + spawn / spawn_browser 开场能力。"""

    __slots__ = ("page", "open_session", "open_browser_session", "playwright_id")

    def __init__(
        self,
        page: Page,
        open_session: Callable[[], BrowserSession],
        open_browser_session: Callable[..., tuple[
            BrowserSession,
            Callable[[], BrowserSession],
            Callable[..., Any],
        ]],
        playwright_id: int,
    ) -> None:
        self.page = page
        self.open_session = open_session
        self.open_browser_session = open_browser_session
        self.playwright_id = playwright_id


@pytest.fixture
def _pilot_page_runtime(
    pilot_browser: SharedBrowser,
    pilot_config: PilotConfig,
    artifacts: ArtifactCollector | None,
    request: pytest.FixtureRequest,
) -> Generator[_PilotPageRuntime, None, None]:
    """主 Context + spawn / spawn_browser；teardown 关闭本用例全部 session。"""
    settings = pilot_config.browser
    sessions: list[BrowserSession] = []
    # 与 sessions 一一对应，供失败截图命名（primary / spawn-N / browser-N / isolated-N）
    failure_names: list[str] = []
    spawn_count = 0
    browser_count = 0
    isolated_count = 0
    # isolated 专属线程：session.close 之后再 stop
    pw_threads_to_stop: list[Any] = []
    artifacts_dir = None if artifacts is None else artifacts.root

    def open_session() -> BrowserSession:
        """在主 Browser 上开 Context（首条为 primary，其后为 spawn）。"""
        nonlocal spawn_count
        if not sessions:
            trace_name = "trace"
            fail_name = "failure"
        else:
            spawn_count += 1
            trace_name = f"trace-spawn-{spawn_count}"
            fail_name = f"failure-spawn-{spawn_count}"
        session = open_page(
            pilot_browser,
            settings,
            artifacts_dir=artifacts_dir,
            trace_name=trace_name,
        )
        sessions.append(session)
        failure_names.append(fail_name)
        return session

    def make_open_browser_session(playwright, pw_thread=None):
        """按给定 Playwright（及可选专属线程）生成 spawn_browser opener。"""

        def open_browser_session(*, isolated: bool = False):
            nonlocal browser_count, spawn_count, isolated_count
            if isolated:
                isolated_count += 1
                session, thr = launch_isolated_session(
                    settings,
                    artifacts_dir=artifacts_dir,
                    trace_name=f"trace-isolated-{isolated_count}",
                )
                sessions.append(session)
                failure_names.append(f"failure-isolated-{isolated_count}")
                pw_threads_to_stop.append(thr)

                def open_on_iso() -> BrowserSession:
                    nonlocal spawn_count
                    spawn_count += 1

                    def _open() -> BrowserSession:
                        wrapper = SharedBrowser(
                            playwright=session.playwright, browser=session.browser
                        )
                        s = open_page(
                            wrapper,
                            settings,
                            artifacts_dir=artifacts_dir,
                            trace_name=f"trace-spawn-{spawn_count}",
                        )
                        s.pw_thread = thr
                        return s

                    s = thr.call(_open)
                    sessions.append(s)
                    failure_names.append(f"failure-spawn-{spawn_count}")
                    return s

                return session, open_on_iso, make_open_browser_session(
                    session.playwright, thr
                )

            browser_count += 1

            def _launch_extra():
                extra = launch_extra_browser(playwright, settings)
                wrapper = SharedBrowser(playwright=playwright, browser=extra)
                s = open_page(
                    wrapper,
                    settings,
                    artifacts_dir=artifacts_dir,
                    trace_name=f"trace-browser-{browser_count}",
                )
                # 关 Browser，但不停 Playwright（非 isolated）
                s.owns_browser = True
                s.owns_playwright = False
                s.pw_thread = pw_thread
                return s, wrapper

            if pw_thread is not None:
                session, wrapper = pw_thread.call(_launch_extra)
            else:
                session, wrapper = _launch_extra()
            sessions.append(session)
            failure_names.append(f"failure-browser-{browser_count}")

            def open_on_extra() -> BrowserSession:
                """子 Flow 的 spawn()：落在该额外 Browser 上。"""
                nonlocal spawn_count
                spawn_count += 1

                def _open() -> BrowserSession:
                    s = open_page(
                        wrapper,
                        settings,
                        artifacts_dir=artifacts_dir,
                        trace_name=f"trace-spawn-{spawn_count}",
                    )
                    s.pw_thread = pw_thread
                    return s

                s = pw_thread.call(_open) if pw_thread is not None else _open()
                sessions.append(s)
                failure_names.append(f"failure-spawn-{spawn_count}")
                return s

            return session, open_on_extra, make_open_browser_session(
                playwright, pw_thread
            )

        return open_browser_session

    root_open_browser = make_open_browser_session(pilot_browser.playwright)

    primary = open_session()
    # 没开 --report 不绑截图；有报告时断言失败即时截，teardown 再兜底
    if artifacts is not None:
        bind_failure_capture(
            primary.page,
            artifacts,
            enabled=settings.screenshot_on_failure,
        )
    failed = False
    try:
        yield _PilotPageRuntime(
            page=primary.page,
            open_session=open_session,
            open_browser_session=root_open_browser,
            playwright_id=id(pilot_browser.playwright),
        )
    except Exception:
        failed = True
        raise
    finally:
        # request.node.rep_call is set by pytest_runtest_makereport hook below
        rep = getattr(request.node, "rep_call", None)
        if rep is not None:
            failed = failed or rep.failed
        if artifacts is not None and settings.screenshot_on_failure and failed:
            for i, session in enumerate(sessions):
                # 主 page 若断言路径已截过则跳过，避免与 assert_failure/soft_N 重复
                if i == 0 and was_assertion_screenshot_taken():
                    continue
                name = failure_names[i]

                def _shot(s=session, n=name):
                    artifacts.screenshot(s.page, n)

                try:
                    if session.pw_thread is not None:
                        session.pw_thread.call(_shot)
                    else:
                        _shot()
                except Exception as exc:
                    logger.debug("failure screenshot %s failed: %s", name, exc)
        clear_failure_capture()
        keep_trace = settings.trace == "on" or (
            settings.trace == "retain-on-failure" and failed
        )
        # 后开的先关；owns_browser 的 session.close 会关额外 Browser / isolated Playwright
        for session in reversed(sessions):
            try:
                if session.pw_thread is not None:
                    session.pw_thread.call(
                        lambda s=session: finalize_trace(s, keep=keep_trace)
                    )
                else:
                    finalize_trace(session, keep=keep_trace)
            finally:
                if session.pw_thread is not None:
                    session.pw_thread.call(session.close)
                else:
                    session.close()
        for thr in pw_threads_to_stop:
            thr.stop()


@pytest.fixture
def pilot_page(_pilot_page_runtime: _PilotPageRuntime) -> Generator[Page, None, None]:
    """每条用例新建 Context 与 Page；浏览器进程来自 session 级 pilot_browser。"""
    yield _pilot_page_runtime.page


@pytest.fixture
def flow_factory() -> Callable[..., BaseFlow] | None:
    """Product conftest should override this fixture to return a Flow factory."""
    return None


@pytest.fixture
def flow(
    pilot_page: Page,
    pilot_config: PilotConfig,
    flow_factory: Callable[..., BaseFlow] | None,
    auth_provider,
    _pilot_page_runtime: _PilotPageRuntime,
) -> BaseFlow:
    if flow_factory is None:
        raise pytest.UsageError(
            "No flow_factory fixture provided. "
            "In your product conftest.py define:\n\n"
            "  @pytest.fixture\n"
            "  def flow_factory():\n"
            "      return Flow\n"
        )
    root = flow_factory(pilot_page, pilot_config)
    root.auth_provider = auth_provider
    # spawn=同 Browser 开 Context；spawn_browser=再启 Browser（可选 isolated 新 Playwright）
    root.bind_spawner(
        flow_factory,
        pilot_config,
        _pilot_page_runtime.open_session,
        _pilot_page_runtime.open_browser_session,
        playwright_id=_pilot_page_runtime.playwright_id,
    )
    return root


def _resolve_base_url(config: pytest.Config) -> str:
    """尽力取 ``browser.base_url``，写入 HTML Environment。"""
    try:
        return str(_load_pilot_config(config).browser.base_url or "").strip()
    except Exception as exc:
        logger.debug("could not resolve base_url for report env: %s", exc)
        return ""


def _apply_html_environment(config: pytest.Config) -> None:
    """HTML Environment 只保留 ``base_url`` 与框架查到的版本，再让产品钩子追加其它字段。"""
    try:
        from pytest_metadata.plugin import metadata_key
    except ImportError:
        return
    try:
        meta = config.stash[metadata_key]
    except KeyError:
        return
    meta.clear()
    base_url = _resolve_base_url(config)
    if base_url:
        meta["base_url"] = base_url
    # pytest-html 在 sessionstart(trylast) 按引用快照这份 dict；追加必须发生在此之前
    from pilot.report.version import fill_report_version

    fill_report_version(meta, config)
    try:
        config.hook.pytest_pilot_report_metadata(metadata=meta, config=config)
    except Exception as exc:
        logger.warning("report metadata hook failed: %s", exc)


@pytest.fixture(autouse=True)
def _pilot_bind_test_item(request: pytest.FixtureRequest):
    """每个用例绑定 item，供 flow.step / extras 写入报告。"""
    token = bind_test_item(request.node)
    try:
        yield
    finally:
        reset_test_item(token)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    """记录各阶段 report；挂 Case 列 / 步骤详情；teardown 后再挂失败产物。"""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)

    meta = resolve_case_meta(item, warn=False)
    report.pilot_case_id = meta.case_id  # type: ignore[attr-defined]
    report.pilot_case_title = meta.title  # type: ignore[attr-defined]
    report.pilot_priority = meta.priority or ""  # type: ignore[attr-defined]
    report.pilot_detail_html = ""  # type: ignore[attr-defined]

    attach_details = report.when == "call" or (
        report.when in ("setup", "teardown") and report.failed
    )
    if attach_details:
        if meta.any and report.when == "call":
            props = list(getattr(report, "user_properties", None) or [])
            props.extend(user_properties_for_meta(meta))
            report.user_properties = props

        extras = pop_html_extras(item) if report.when == "call" else []
        steps = pop_steps(item) if report.when == "call" else []
        detail = render_case_detail_html(
            case_id=meta.case_id,
            title=meta.title,
            priority=meta.priority,
            steps=steps,
        )
        report.pilot_detail_html = (  # type: ignore[attr-defined]
            detail if (meta.any or steps) else ""
        )
        if extras:
            report.extras = getattr(report, "extras", []) + extras

    # fixture teardown 在 call 报告之后；等 teardown 阶段再挂，避免缺 trace/兜底截图
    if report.when == "teardown":
        attach_failure_artifacts(item)


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_header(cells: list[str]) -> None:
    """插入 Case ID / Priority / Title 列，无需展开即可看到用例文字。"""
    cells.insert(2, '<th class="sortable" data-column-type="caseId">Case ID</th>')
    cells.insert(3, '<th class="sortable" data-column-type="priority">Priority</th>')
    cells.insert(4, '<th class="sortable" data-column-type="caseTitle">Title</th>')


@pytest.hookimpl(optionalhook=True)
def pytest_html_results_table_row(report: Any, cells: list[str]) -> None:
    from html import escape

    case_id = escape(str(getattr(report, "pilot_case_id", "") or ""))
    priority = escape(str(getattr(report, "pilot_priority", "") or ""))
    title = str(getattr(report, "pilot_case_title", "") or "")
    detail = str(getattr(report, "pilot_detail_html", "") or "")
    cells.insert(2, f'<td class="col-caseId">{case_id}</td>')
    cells.insert(3, f'<td class="col-priority">{priority}</td>')
    cells.insert(4, render_title_cell_html(title=title, detail_html=detail))


def _collect_session_summary(session: pytest.Session, duration_sec: float) -> SessionSummary:
    """从 terminalreporter.stats 汇总会话结果（含失败 nodeid）。"""
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    stats: dict[str, list[Any]] = getattr(reporter, "stats", {}) if reporter else {}

    def _count(key: str) -> int:
        return len(stats.get(key, []) or [])

    failed_names: list[str] = []
    for key in ("failed", "error"):
        for rep in stats.get(key, []) or []:
            nodeid = getattr(rep, "nodeid", None)
            if nodeid:
                failed_names.append(str(nodeid))

    return SessionSummary(
        passed=_count("passed"),
        failed=_count("failed"),
        skipped=_count("skipped"),
        error=_count("error"),
        duration_sec=duration_sec,
        failed_names=failed_names,
    )


def _maybe_notify_feishu(pilot_config: PilotConfig, summary: SessionSummary) -> None:
    """已启用飞书时发送会话汇总；未启用则跳过。"""
    if not pilot_config.feishu.enabled:
        return
    notify_session_summary(pilot_config.feishu, summary, env=pilot_config.env)


def pytest_sessionstart(session: pytest.Session) -> None:
    """记录会话开始时间；在 pytest-html 快照 Environment 前写入 base_url。"""
    setattr(session.config, _SESSION_START_ATTR, time.time())
    _apply_html_environment(session.config)


@pytest.hookimpl(hookwrapper=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int):
    """会话结束：先让 pytest-html 写盘，再 polish 归档；最后飞书汇总。"""
    yield
    run_dir = finalize_report_archive(session.config)
    if run_dir is not None:
        logger.info("html report archived at %s", run_dir)
    del exitstatus  # 通知与退出码解耦
    start = getattr(session.config, _SESSION_START_ATTR, None)
    duration = (time.time() - start) if isinstance(start, (int, float)) else 0.0
    summary = _collect_session_summary(session, duration)
    try:
        pilot_config = _load_pilot_config(session.config)
    except Exception as exc:
        logger.debug("skip feishu notify; config load failed: %s", exc)
        return
    _maybe_notify_feishu(pilot_config, summary)


def _apply_from_report_filter(config: pytest.Config, items: list[pytest.Item]) -> None:
    """``--from-report``：只保留报告中 Failed/Error 对应的已收集用例。"""
    report_path = getattr(config.option, "pilot_from_report", None)
    if not report_path:
        return
    try:
        wanted = extract_failed_nodeids(report_path)
        kept, deselected = deselect_not_in_report(items, wanted)
    except FromReportError as exc:
        pytest.exit(str(exc), returncode=2)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept
    missing = unmatched_wanted(wanted, kept)
    if missing:
        sample = ", ".join(missing[:5])
        more = "" if len(missing) <= 5 else f" (+{len(missing) - 5} more)"
        logger.warning(
            "from-report: %d failed/error nodeid(s) not in collection: %s%s",
            len(missing),
            sample,
            more,
        )
    logger.info(
        "from-report: keeping %d / %d collected test(s) from %s",
        len(kept),
        len(kept) + len(deselected),
        report_path,
    )


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """device / priority / from-report 过滤 + cases 层禁止直接使用 page/playwright。"""
    del session  # 签名对齐 pytest hook

    # 同一用例挂多个 P0–P3 时在收集阶段失败
    for item in items:
        try:
            marker_priority(item)
        except ValueError as exc:
            raise pytest.UsageError(f"{item.nodeid}: {exc}") from exc

    env = _resolve_active_env(config)
    if env:
        kept, deselected = deselect_for_env(items, env)
        if deselected:
            config.hook.pytest_deselected(items=deselected)
            items[:] = kept
            logger.info(
                "device filter: env=%s deselected %d test(s)",
                env,
                len(deselected),
            )

    # --priority 未传则不筛；传入后仅保留级别命中的用例（未打标剔除）
    try:
        priorities = parse_priority_cli(config.getoption("pilot_priority"))
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc
    if priorities:
        kept, deselected = deselect_for_priority(items, priorities)
        if deselected:
            config.hook.pytest_deselected(items=deselected)
            items[:] = kept
            logger.info(
                "priority filter: allowed=%s deselected %d test(s)",
                ",".join(sorted(priorities)),
                len(deselected),
            )

    # 在 device / priority 之后按报告 Failed/Error 再筛
    _apply_from_report_filter(config, items)

    violations: list[str] = []
    for item in items:
        path = Path(str(item.fspath))
        if "cases" not in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        banned = []
        for needle in (
            "from playwright",
            "import playwright",
            "from pages.",
            "import pages",
            ".locator(",
            "get_by_test_id(",
        ):
            if needle in text:
                banned.append(needle)
        if banned:
            violations.append(f"{path}: forbidden in case layer: {', '.join(banned)}")

    if violations:
        raise pytest.UsageError(
            "Case layer must only use flow/business actions.\n" + "\n".join(violations)
        )
