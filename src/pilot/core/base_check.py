"""Base check：业务断言入口；UI / DB 断言统一走 assertx。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from playwright.sync_api import Locator, Page

from pilot.core import locate
from pilot.core import assertx
from pilot.core.locate import MatchMode

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pilot.core.config import BrowserSettings


class BaseCheck:
    """产品 Check 继承此类。

    - **UI**：``expect_visible`` / ``expect_text`` 等接受 ``Locator | str``，
      负责 resolve / ``match`` / 默认超时，再委托 ``assertx``（Playwright expect + 软断言）。
    - **DB / 通用值**：同名方法直接转发 ``assertx``，Check 内统一 ``self.expect_*``，
      不必再记两套入口。

    Page 只提供命名 locator 与动作；**不要**在 Page 上写 ``expect_*``。
    """

    def __init__(self, page: Page, settings: BrowserSettings) -> None:
        self.page = page
        self.settings = settings

    # ------------------------------------------------------------------
    # UI（定位收窄 + assertx）
    # ------------------------------------------------------------------

    def expect_visible(
        self,
        target: Locator | str,
        *,
        timeout: float | None = None,
        match: MatchMode = "strict",
        message: str | None = None,
    ) -> None:
        """断言元素可见。"""
        assertx.expect_visible(
            self._target(target, match),
            timeout=self._timeout(timeout),
            message=message,
        )

    def expect_text(
        self,
        target: Locator | str,
        text: str,
        *,
        timeout: float | None = None,
        match: MatchMode = "strict",
        message: str | None = None,
    ) -> None:
        """断言元素文本。"""
        assertx.expect_text(
            self._target(target, match),
            text,
            timeout=self._timeout(timeout),
            message=message,
        )

    def expect_value(
        self,
        target: Locator | str,
        value: str,
        *,
        timeout: float | None = None,
        match: MatchMode = "strict",
        message: str | None = None,
    ) -> None:
        """断言输入框等 value。"""
        assertx.expect_value(
            self._target(target, match),
            value,
            timeout=self._timeout(timeout),
            message=message,
        )

    def expect_attribute(
        self,
        target: Locator | str,
        name: str,
        value: str,
        *,
        timeout: float | None = None,
        match: MatchMode = "strict",
        message: str | None = None,
    ) -> None:
        """断言元素属性。"""
        assertx.expect_attribute(
            self._target(target, match),
            name,
            value,
            timeout=self._timeout(timeout),
            message=message,
        )

    def expect_hidden(
        self,
        target: Locator | str,
        *,
        timeout: float | None = None,
        match: MatchMode = "strict",
        message: str | None = None,
    ) -> None:
        """断言元素隐藏。"""
        assertx.expect_hidden(
            self._target(target, match),
            timeout=self._timeout(timeout),
            message=message,
        )

    def expect_count(
        self,
        target: Locator | str,
        count: int,
        *,
        timeout: float | None = None,
        message: str | None = None,
    ) -> None:
        """断言匹配数量（不应用 match 收窄）。"""
        assertx.expect_count(
            self._resolve(target),
            count,
            timeout=self._timeout(timeout),
            message=message,
        )

    def expect_url_contains(
        self,
        fragment: str,
        *,
        timeout: float | None = None,
        message: str | None = None,
    ) -> None:
        """断言当前 URL 包含片段。"""
        assertx.expect_url_contains(
            self.page,
            fragment,
            timeout=self._timeout(timeout),
            message=message,
        )

    # ------------------------------------------------------------------
    # DB / 通用值（原样转发 assertx，统一 self.expect_* 用法）
    # ------------------------------------------------------------------

    def expect_not_none(self, value: Any, *, message: str | None = None) -> None:
        """断言值不为 None。"""
        assertx.expect_not_none(value, message=message)

    def expect_none(self, value: Any, *, message: str | None = None) -> None:
        """断言值为 None。"""
        assertx.expect_none(value, message=message)

    def expect_row(
        self,
        row: Mapping[str, Any] | None,
        expected: Mapping[str, Any],
        *,
        allow_extra: bool = True,
    ) -> None:
        """断言单行 dict 包含 expected 字段。"""
        assertx.expect_row(row, expected, allow_extra=allow_extra)

    def expect_rows_count(self, rows: Sequence[Any], count: int) -> None:
        """断言列表长度等于 count。"""
        assertx.expect_rows_count(rows, count)

    def expect_rows_count_at_least(self, rows: Sequence[Any], count: int) -> None:
        """断言列表长度 >= count。"""
        assertx.expect_rows_count_at_least(rows, count)

    def expect_rows_count_at_most(self, rows: Sequence[Any], count: int) -> None:
        """断言列表长度 <= count。"""
        assertx.expect_rows_count_at_most(rows, count)

    def expect_rows_equal(
        self,
        rows: Sequence[Mapping[str, Any]],
        expected: Sequence[Mapping[str, Any]],
        *,
        allow_extra: bool = True,
    ) -> None:
        """按顺序逐行子集比对。"""
        assertx.expect_rows_equal(rows, expected, allow_extra=allow_extra)

    def expect_rows_contain(
        self,
        rows: Sequence[Mapping[str, Any]],
        subset: Mapping[str, Any],
    ) -> None:
        """断言存在至少一行包含 subset。"""
        assertx.expect_rows_contain(rows, subset)

    # ------------------------------------------------------------------
    # 内部：与 BasePage 对齐的定位解析（断言侧独立一份，避免 Page 暴露 expect）
    # ------------------------------------------------------------------

    def _timeout(self, timeout: float | None) -> float:
        return self.settings.timeout_ms if timeout is None else timeout

    def _target(self, target: Locator | str, match: MatchMode) -> Locator:
        return locate.apply_match(self._resolve(target), match)

    def _resolve(self, target: Locator | str) -> Locator:
        return locate.resolve(self.page, target)
