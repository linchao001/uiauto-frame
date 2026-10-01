"""Flow base: product repos assemble Actions onto a Flow subclass."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import urljoin

from pilot.core.logging import StepLogger
from pilot.core.storage import install_local_storage

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from pilot.account.auth import AuthProvider
    from pilot.core.browser import BrowserSession
    from pilot.core.config import PilotConfig

F = TypeVar("F", bound="BaseFlow")

# open_browser_session(*, isolated) -> (session, open_ctx, open_browser_for_this_pw)
OpenBrowserSession = Callable[
    ...,
    tuple[
        "BrowserSession",
        Callable[[], "BrowserSession"],
        Callable[..., tuple["BrowserSession", Callable[[], "BrowserSession"], Any]],
    ],
]


class BaseFlow:
    """用例入口 ``flow``。

    产品仓应子类化并挂载 Actions，例如::

        class Flow(BaseFlow):
            def __init__(self, page, config, *, auth=None):
                super().__init__(page, config, auth=auth)
                self.order = OrderActions(self)
    """

    def __init__(
        self,
        page: Page,
        config: PilotConfig,
        *,
        auth: AuthProvider | None = None,
    ) -> None:
        self.page = page
        self.config = config
        # 鉴权由产品 AuthProvider 提供；pytest flow fixture 会注入
        # 属性名用 auth_provider，避免与产品侧 AuthActions（常挂 self.auth）冲突
        self.auth_provider = auth
        self.steps = StepLogger()
        # pytest ``flow`` fixture 会 bind_spawner；手工构造时 spawn / spawn_browser 不可用
        self._spawner: Callable[[], BaseFlow] | None = None
        self._browser_spawner: Callable[..., BaseFlow] | None = None
        # 供 run_concurrent 闭包冲突检测；bind_spawner 时写入
        self._playwright_id: int | None = None
        # isolated Flow：Page 操作须在专属 PlaywrightThread 上（经 run_concurrent 投递）
        self._pw_thread: Any | None = None

    def account(self, role: str | None = None) -> dict[str, str]:
        """按角色取账号；``role`` 为空时用 ``config.default_account``。"""
        resolved = role if role is not None else self.config.default_account
        try:
            return self.config.accounts[resolved]
        except KeyError as exc:
            known = ", ".join(sorted(self.config.accounts)) or "(none)"
            raise KeyError(f"Unknown account role {resolved!r}. Known: {known}") from exc

    def open_as(self, role: str, page_url: str) -> None:
        """按账号角色做接口登录后打开页面。

        ``role`` 为 ``accounts`` 配置 key。
        ``page_url`` 为站内路径或绝对 URL。页面就绪（``wait_ready``）由产品侧负责。
        鉴权协议由已注入的 ``AuthProvider.login`` / ``token_store_items`` 实现。
        """
        if self.auth_provider is None:
            raise RuntimeError(
                "BaseFlow.open_as 需要 AuthProvider："
                "请在 conftest 注册并经 flow fixture 注入（见 pilot init）。"
            )
        base_url = self.config.browser.base_url
        account = self.account(role)
        data = self.auth_provider.login(
            base_url=base_url,
            username=account["username"],
            password=account["password"],
        )
        items = self.auth_provider.token_store_items(data)
        # 首屏脚本前注入，避免 SPA 用空 token 覆盖
        install_local_storage(self.page.context, items)
        target = urljoin(base_url.rstrip("/") + "/", page_url.lstrip("/"))
        self.page.goto(target, wait_until="domcontentloaded")

    def step(self, name: str, *, report: bool = True):
        """步骤上下文：默认写入报告；Action 内部过程传 ``report=False`` 仅打日志。"""
        return self.steps.step(name, report=report)

    def bind_spawner(
        self,
        flow_factory: Callable[..., BaseFlow],
        config: PilotConfig,
        open_session: Callable[[], BrowserSession],
        open_browser_session: OpenBrowserSession,
        playwright_id: int | None = None,
        pw_thread: Any | None = None,
    ) -> None:
        """挂上 spawn（同 Browser 开 Context）与 spawn_browser（再启 Browser）。

        ``open_session``：在当前 Flow 所属 Browser 上新建 Context。
        ``open_browser_session(*, isolated)``：返回三元组
        ``(首个 session, 该 Browser 上再开 Context, 该 Playwright 上再 spawn_browser 的 opener)``。
        产生的 session 均由调用方（pytest 插件）负责回收。
        """
        if playwright_id is not None:
            self._playwright_id = playwright_id
        if pw_thread is not None:
            self._pw_thread = pw_thread

        def _spawn() -> BaseFlow:
            session = open_session()
            child = flow_factory(session.page, config)
            # 子 flow 复用同一 AuthProvider
            child.auth_provider = self.auth_provider
            # 子 flow 同样可再 spawn / spawn_browser；继承所属 PW 线程
            child.bind_spawner(
                flow_factory,
                config,
                open_session,
                open_browser_session,
                playwright_id=id(session.playwright),
                pw_thread=session.pw_thread or self._pw_thread,
            )
            return child

        def _spawn_browser(*, isolated: bool = False) -> BaseFlow:
            session, child_open_session, child_open_browser = open_browser_session(
                isolated=isolated
            )
            child = flow_factory(session.page, config)
            child.auth_provider = self.auth_provider
            # 第三项：子树再 spawn_browser 必须落在该 session 所属 Playwright
            child.bind_spawner(
                flow_factory,
                config,
                child_open_session,
                child_open_browser,
                playwright_id=id(session.playwright),
                pw_thread=session.pw_thread,
            )
            return child

        self._spawner = _spawn
        self._browser_spawner = _spawn_browser

    def spawn(self: F) -> F:
        """在同一浏览器进程上新开 Context/Page，返回同型 Flow（独立浏览器会话）。

        典型用法::

            left = flow
            right = flow.spawn()
            left.open_as("test_user", "/home")
            right.open_as("test_user", "/home")

        仅在 pytest ``flow`` fixture（或测试里自行 ``bind_spawner``）下可用。
        """
        if self._spawner is None:
            raise RuntimeError(
                "flow.spawn() is unavailable: use the pytest ``flow`` fixture "
                "(or call bind_spawner in harness tests)."
            )
        return self._spawner()  # type: ignore[return-value]

    def spawn_browser(self: F, *, isolated: bool = False) -> F:
        """再启浏览器进程，返回同型 Flow。

        ``isolated=False``（默认）：复用当前 Playwright，再 launch Browser（串行真多开）。
        ``isolated=True``：新建 Playwright + Browser（线程并发就绪）。

        典型用法::

            admin = flow
            other = flow.spawn_browser()
            # 真并发：
            # a = flow.spawn_browser(isolated=True)
            # b = flow.spawn_browser(isolated=True)
            # flow.run_concurrent(lambda: a...., lambda: b....)

        仅 cookie 隔离请用 ``spawn()``。
        仅在 pytest ``flow`` fixture（或测试里自行 ``bind_spawner``）下可用。
        """
        if self._browser_spawner is None:
            raise RuntimeError(
                "flow.spawn_browser() is unavailable: use the pytest ``flow`` fixture "
                "(or call bind_spawner in harness tests)."
            )
        return self._browser_spawner(isolated=isolated)  # type: ignore[return-value]

    def run_concurrent(
        self,
        *fns: Callable[[], Any],
        timeout: float | None = None,
    ) -> tuple[Any, ...]:
        """多线程齐射执行 ``fns``（产品无关原语）。

        参与方须使用不同 Playwright（通常 ``spawn_browser(isolated=True)``）；
        主 ``flow`` 不要在工作线程里驱动页面。详见 ``pilot.flow.concurrent``。
        """
        from pilot.flow.concurrent import run_concurrent as _run

        return _run(*fns, timeout=timeout)
