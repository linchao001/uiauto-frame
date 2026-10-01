"""Base page object with stable interactions."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from playwright.sync_api import Locator, Page

from pilot.core import locate
from pilot.core.locate import MatchMode
from pilot.core.logging import get_logger
from pilot.core.retry import action_timeout_ms, retry_action

if TYPE_CHECKING:
    from pilot.core.config import BrowserSettings

logger = get_logger("pilot")


class BasePage:
    """页面对象基类：定位与动作。断言请用 ``BaseCheck`` / ``assertx``。"""

    path: str = ""

    def __init__(self, page: Page, settings: BrowserSettings) -> None:
        self.page = page
        self.settings = settings

    @property
    def url(self) -> str:
        base = self.settings.base_url.rstrip("/") + "/"
        return urljoin(base, self.path.lstrip("/"))

    def open(self) -> None:
        self.page.goto(self.url, wait_until="domcontentloaded")
        self.wait_ready()

    def wait_ready(self) -> None:
        """等待页面业务就绪。

        默认仅等到 ``domcontentloaded``（与 ``open`` 的 goto 对齐）。
        业务 Page 应覆盖本方法，等待真实就绪信号（关键选择器 / 接口 / 骨架屏消失等），
        避免在断言前依赖隐式 sleep。
        """
        self.page.wait_for_load_state("domcontentloaded")

    def locator(self, selector: str) -> Locator:
        return self.page.locator(selector)

    def by_testid(self, test_id: str) -> Locator:
        return self.page.get_by_test_id(test_id)

    def by_role(self, role: str, **kwargs) -> Locator:
        return self.page.get_by_role(role, **kwargs)

    def by_label(self, text: str, **kwargs) -> Locator:
        return self.page.get_by_label(text, **kwargs)

    def by_placeholder(self, text: str, **kwargs) -> Locator:
        return self.page.get_by_placeholder(text, **kwargs)

    def by_text(self, text: str, **kwargs) -> Locator:
        return self.page.get_by_text(text, **kwargs)

    def by_alt_text(self, text: str, **kwargs) -> Locator:
        return self.page.get_by_alt_text(text, **kwargs)

    def by_title(self, text: str, **kwargs) -> Locator:
        return self.page.get_by_title(text, **kwargs)

    def within(self, root: Locator | str, child: str) -> Locator:
        return locate.within(self._resolve(root), child)

    def filter_has_text(self, target: Locator | str, text: str) -> Locator:
        return locate.filter_has_text(self._resolve(target), text)

    def nth(self, target: Locator | str, index: int) -> Locator:
        return locate.nth(self._resolve(target), index)

    def click(
        self,
        target: Locator | str,
        *,
        name: str | None = None,
        match: MatchMode = "strict",
    ) -> None:
        locator = self._target(target, match)
        label = name or self._describe(locator)
        logger.debug("click: %s", label)
        self._run_action(label, "click", lambda timeout: locator.click(timeout=timeout))

    def fill(
        self,
        target: Locator | str,
        value: str,
        *,
        name: str | None = None,
        match: MatchMode = "strict",
    ) -> None:
        locator = self._target(target, match)
        label = name or self._describe(locator)
        logger.debug("fill: %s = %r", label, value)
        self._run_action(label, "fill", lambda timeout: locator.fill(value, timeout=timeout))

    def select_option(
        self,
        target: Locator | str,
        value: str,
        *,
        name: str | None = None,
        match: MatchMode = "strict",
    ) -> None:
        locator = self._target(target, match)
        label = name or self._describe(locator)
        self._run_action(
            label, "select", lambda timeout: locator.select_option(value, timeout=timeout)
        )

    def scroll_into_view(
        self,
        target: Locator | str,
        *,
        name: str | None = None,
        match: MatchMode = "strict",
    ) -> None:
        """将目标滚入可见区域（含嵌套滚动容器）。

        页面长列表与容器内子元素均可：容器场景先用 ``within`` 收窄再调用本方法。
        """
        locator = self._target(target, match)
        label = name or self._describe(locator)
        logger.debug("scroll_into_view: %s", label)
        self._run_action(
            label,
            "scroll_into_view",
            lambda timeout: locator.scroll_into_view_if_needed(timeout=timeout),
        )

    def _run_action(self, label: str, verb: str, run: Callable[[float], None]) -> None:
        """执行一次操作：瞬态失败可重试；重试用半额超时控制墙钟时间。"""
        attempt = 0

        def _do() -> None:
            nonlocal attempt
            timeout = action_timeout_ms(self.settings.timeout_ms, attempt)
            attempt += 1
            run(timeout)

        retry_action(
            _do,
            retries=self.settings.action_retries,
            delay_ms=self.settings.action_retry_delay_ms,
            on_retry=lambda n, e: logger.warning("retry %s %s (#%s): %s", verb, label, n, e),
        )

    def _target(self, target: Locator | str, match: MatchMode) -> Locator:
        return locate.apply_match(self._resolve(target), match)

    def _resolve(self, target: Locator | str) -> Locator:
        return locate.resolve(self.page, target)

    @staticmethod
    def _describe(locator: Locator) -> str:
        try:
            return str(locator)
        except Exception:  # noqa: BLE001
            return "<locator>"
