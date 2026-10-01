"""浏览器进程与单条用例 context 的生命周期。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from pilot.core.config import BrowserSettings


@dataclass
class SharedBrowser:
    """整场（每 worker）共用的 Playwright + 主浏览器进程。close 才停 Playwright。

    单用例多用户：``flow.spawn`` 开 Context；``flow.spawn_browser`` 在同一 Playwright
    上再 launch Browser。不要另起一套 Playwright。
    """

    playwright: Playwright
    browser: Browser

    def close(self) -> None:
        """关掉浏览器进程并停止 Playwright。用例 teardown 不要调用。"""
        try:
            self.browser.close()
        finally:
            self.playwright.stop()


@dataclass
class BrowserSession:
    """一条用例的 Context 与 Page。默认不拥有浏览器进程。"""

    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page
    trace_path: Path | None = None
    # launch_session / spawn_browser 自带进程时为 True；主 SharedBrowser 上的 session 为 False
    owns_browser: bool = False
    # 仅 launch_session / isolated：close 时连 Playwright 一并 stop；非 isolated spawn_browser 为 False
    owns_playwright: bool = False
    # isolated：Page 只能在该线程 call 内使用；teardown 也须经该线程 close
    pw_thread: Any | None = None

    def close(self) -> None:
        """关掉本用例 context。owns_browser 时关 Browser；owns_playwright 时再 stop Playwright。"""
        try:
            self.context.close()
        finally:
            if self.owns_browser:
                try:
                    self.browser.close()
                finally:
                    if self.owns_playwright:
                        self.playwright.stop()


def _launch_kwargs(settings: BrowserSettings) -> dict[str, Any]:
    """从配置拼 launch 参数（主浏览器与额外浏览器共用）。"""
    launch_kwargs: dict[str, Any] = {
        "headless": settings.headless,
        "slow_mo": settings.slow_mo,
    }
    if settings.channel:
        launch_kwargs["channel"] = settings.channel
    return launch_kwargs


def launch_browser(settings: BrowserSettings) -> SharedBrowser:
    """启动一次 Playwright 与 Browser，供整场测试复用。"""
    pw = sync_playwright().start()
    browser_type = getattr(pw, settings.browser)
    browser = browser_type.launch(**_launch_kwargs(settings))
    return SharedBrowser(playwright=pw, browser=browser)


def launch_extra_browser(playwright: Playwright, settings: BrowserSettings) -> Browser:
    """在已有 Playwright 上再 launch 一个 Browser（供 spawn_browser）。

    调用方负责 ``browser.close()``；不得因此 stop Playwright。
    """
    browser_type = getattr(playwright, settings.browser)
    return browser_type.launch(**_launch_kwargs(settings))


def launch_isolated_session(
    settings: BrowserSettings,
    *,
    artifacts_dir: str | Path | None = None,
    trace_name: str = "trace",
) -> tuple[BrowserSession, "PlaywrightThread"]:
    """在专属线程上 start 一套 Playwright + Browser + Context。

    sync API 同线程不能二次 ``sync_playwright().start()``，故 isolated 必须走本路径。
    返回的 session 仅可在该 ``PlaywrightThread.call`` 内操作 Page。
    """
    from pilot.core.pw_thread import PlaywrightThread

    thr = PlaywrightThread()

    def _boot() -> BrowserSession:
        shared = launch_browser(settings)
        session = open_page(
            shared,
            settings,
            artifacts_dir=artifacts_dir,
            trace_name=trace_name,
        )
        session.owns_browser = True
        session.owns_playwright = True
        return session

    try:
        session = thr.call(_boot)
    except Exception:
        thr.stop()
        raise
    session.pw_thread = thr
    return session, thr


def open_page(
    shared: SharedBrowser,
    settings: BrowserSettings,
    *,
    artifacts_dir: str | Path | None = None,
    trace_name: str = "trace",
) -> BrowserSession:
    """在已有 Browser 上新建 Context 与 Page。关 session 不会关掉 shared。

    ``artifacts_dir`` 为空时不建目录，也不开录像 / trace（没开 ``--report`` 的默认）。
    """
    artifacts = Path(artifacts_dir) if artifacts_dir is not None else None
    if artifacts is not None:
        artifacts.mkdir(parents=True, exist_ok=True)

    context_kwargs: dict[str, Any] = {
        "viewport": {
            "width": settings.viewport_width,
            "height": settings.viewport_height,
        },
        "base_url": settings.base_url or None,
    }
    if artifacts is not None and settings.video in {"on", "retain-on-failure"}:
        context_kwargs["record_video_dir"] = str(artifacts / "videos")

    context = shared.browser.new_context(
        **{k: v for k, v in context_kwargs.items() if v is not None}
    )
    context.set_default_timeout(settings.timeout_ms)
    context.set_default_navigation_timeout(settings.navigation_timeout_ms)

    trace_path: Path | None = None
    if artifacts is not None and settings.trace in {"on", "retain-on-failure"}:
        trace_path = artifacts / f"{trace_name}.zip"
        context.tracing.start(screenshots=True, snapshots=True, sources=True)

    page = context.new_page()
    return BrowserSession(
        playwright=shared.playwright,
        browser=shared.browser,
        context=context,
        page=page,
        trace_path=trace_path,
        owns_browser=False,
        owns_playwright=False,
    )


def launch_session(
    settings: BrowserSettings,
    *,
    artifacts_dir: str | Path | None = None,
    trace_name: str = "trace",
) -> BrowserSession:
    """自带浏览器进程的一次性会话。close 会连进程与 Playwright 一起停掉。

    pytest 路径不要用这个：进程由 session 级 fixture 持有，用例只 open_page。
    """
    shared = launch_browser(settings)
    try:
        session = open_page(
            shared,
            settings,
            artifacts_dir=artifacts_dir,
            trace_name=trace_name,
        )
    except Exception:
        shared.close()
        raise
    session.owns_browser = True
    session.owns_playwright = True
    return session


def finalize_trace(session: BrowserSession, *, keep: bool) -> None:
    if session.trace_path is None:
        return
    if keep:
        session.context.tracing.stop(path=str(session.trace_path))
    else:
        # 通过且 retain-on-failure 时丢掉 trace，避免每条都留 zip
        session.context.tracing.stop()
        if session.trace_path.exists():
            session.trace_path.unlink(missing_ok=True)
