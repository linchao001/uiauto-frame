"""Business-friendly assertions（UI expect + DB/通用值断言）。"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NoReturn

from playwright.sync_api import Locator, Page, expect

from pilot.core.assert_format import (
    format_assertion_failure,
    format_plain_failure,
    wrap_ui_assertion_failure,
)
from pilot.core.logging import get_logger
from pilot.core.soft import run_assertion

logger = get_logger("pilot.assertx")


def _expect(fn: Callable[[], Any]) -> None:
    """统一走软/硬断言调度。"""
    run_assertion(fn)


def _ui_expect(fn: Callable[[], Any], *, message: str | None = None) -> None:
    """执行 UI 断言；失败时包装业务提示与原因归类。"""

    def _run() -> None:
        try:
            fn()
        except AssertionError as exc:
            raise wrap_ui_assertion_failure(exc, message=message) from None

    _expect(_run)


def _raise_formatted(message: str) -> NoReturn:
    """打 error 日志后抛出（pytest / soft 收集共用同一段文案）。"""
    # 按行打，避免 log_cli 把多行 diff 收成一条转义串
    for line in message.splitlines() or [message]:
        logger.error("%s", line)
    raise AssertionError(message)


def _fail(label: str, diffs: list[str]) -> NoReturn:
    """结构化 diff 失败。"""
    _raise_formatted(format_assertion_failure(label, diffs))


def _fail_plain(message: str) -> NoReturn:
    """无结构化 diff 的单行失败。"""
    _raise_formatted(format_plain_failure(message))


def expect_text(
    locator: Locator,
    text: str,
    *,
    timeout: float | None = None,
    message: str | None = None,
) -> None:
    """断言元素文本；``message`` 为失败时的业务提示。"""
    _ui_expect(
        lambda: expect(locator).to_have_text(text, timeout=timeout),
        message=message,
    )


def expect_visible(
    locator: Locator,
    *,
    timeout: float | None = None,
    message: str | None = None,
) -> None:
    """断言元素可见；``message`` 为失败时的业务提示。"""
    _ui_expect(
        lambda: expect(locator).to_be_visible(timeout=timeout),
        message=message,
    )


def expect_url_contains(
    page: Page,
    fragment: str,
    *,
    timeout: float | None = None,
    message: str | None = None,
) -> None:
    """断言 URL 包含片段；``message`` 为失败时的业务提示。"""
    _ui_expect(
        lambda: expect(page).to_have_url(re.compile(re.escape(fragment)), timeout=timeout),
        message=message,
    )


def expect_value(
    locator: Locator,
    value: str,
    *,
    timeout: float | None = None,
    message: str | None = None,
) -> None:
    """断言输入 value；``message`` 为失败时的业务提示。"""
    _ui_expect(
        lambda: expect(locator).to_have_value(value, timeout=timeout),
        message=message,
    )


def expect_attribute(
    locator: Locator,
    name: str,
    value: str,
    *,
    timeout: float | None = None,
    message: str | None = None,
) -> None:
    """断言元素属性；``message`` 为失败时的业务提示。"""
    _ui_expect(
        lambda: expect(locator).to_have_attribute(name, value, timeout=timeout),
        message=message,
    )


def expect_count(
    locator: Locator,
    count: int,
    *,
    timeout: float | None = None,
    message: str | None = None,
) -> None:
    """断言匹配数量；``message`` 为失败时的业务提示。"""
    _ui_expect(
        lambda: expect(locator).to_have_count(count, timeout=timeout),
        message=message,
    )


def expect_hidden(
    locator: Locator,
    *,
    timeout: float | None = None,
    message: str | None = None,
) -> None:
    """断言元素隐藏；``message`` 为失败时的业务提示。"""
    _ui_expect(
        lambda: expect(locator).to_be_hidden(timeout=timeout),
        message=message,
    )


# ---------------------------------------------------------------------------
# DB / 通用值断言（dict / list；不依赖 Playwright）
# ---------------------------------------------------------------------------


def expect_not_none(value: Any, *, message: str | None = None) -> None:
    """断言值不为 None（常用于 select_one 结果）。"""

    def _check() -> None:
        if value is None:
            _fail_plain(message or "expected value to be not None")

    _expect(_check)


def expect_none(value: Any, *, message: str | None = None) -> None:
    """断言值为 None。"""

    def _check() -> None:
        if value is not None:
            if message:
                _fail_plain(message)
            _fail("expect none", [f"value: expected None, got {value!r}"])

    _expect(_check)


def _row_subset_matches(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> list[str]:
    """返回不匹配的字段说明；空列表表示通过。"""
    mismatches: list[str] = []
    for key, exp in expected.items():
        if key not in actual:
            mismatches.append(f"missing key {key!r}")
            continue
        got = actual[key]
        if got != exp:
            mismatches.append(f"{key}: expected {exp!r}, got {got!r}")
    return mismatches


def expect_row(
    row: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
    *,
    allow_extra: bool = True,
) -> None:
    """断言单行 dict 包含 expected 字段（默认允许多余列）。"""

    def _check() -> None:
        if row is None:
            _fail_plain(f"expected row matching {dict(expected)!r}, got None")
        mismatches = _row_subset_matches(row, expected)
        if mismatches:
            _fail("row mismatch", mismatches)
        if not allow_extra:
            extras = sorted(set(row.keys()) - set(expected.keys()))
            if extras:
                _fail("row mismatch", [f"unexpected extra keys: {extras}"])

    _expect(_check)


def expect_rows_count(rows: Sequence[Any], count: int) -> None:
    """断言列表长度等于 count。"""

    def _check() -> None:
        actual = len(rows)
        if actual != count:
            _fail("rows count", [f"count: expected {count}, got {actual}"])

    _expect(_check)


def expect_rows_count_at_least(rows: Sequence[Any], count: int) -> None:
    """断言列表长度 >= count。"""

    def _check() -> None:
        actual = len(rows)
        if actual < count:
            _fail(
                "rows count at least",
                [f"count: expected >= {count}, got {actual}"],
            )

    _expect(_check)


def expect_rows_count_at_most(rows: Sequence[Any], count: int) -> None:
    """断言列表长度 <= count。"""

    def _check() -> None:
        actual = len(rows)
        if actual > count:
            _fail(
                "rows count at most",
                [f"count: expected <= {count}, got {actual}"],
            )

    _expect(_check)


def expect_rows_equal(
    rows: Sequence[Mapping[str, Any]],
    expected: Sequence[Mapping[str, Any]],
    *,
    allow_extra: bool = True,
) -> None:
    """按顺序逐行子集比对；条数必须一致。"""

    def _check() -> None:
        if len(rows) != len(expected):
            _fail(
                "rows equal",
                [f"count: expected {len(expected)}, got {len(rows)}"],
            )
        for idx, (actual, exp) in enumerate(zip(rows, expected, strict=True)):
            mismatches = _row_subset_matches(actual, exp)
            if mismatches:
                _fail(f"rows[{idx}] mismatch", mismatches)
            if not allow_extra:
                extras = sorted(set(actual.keys()) - set(exp.keys()))
                if extras:
                    _fail(
                        f"rows[{idx}] mismatch",
                        [f"unexpected extra keys: {extras}"],
                    )

    _expect(_check)


def expect_rows_contain(
    rows: Sequence[Mapping[str, Any]],
    subset: Mapping[str, Any],
) -> None:
    """断言存在至少一行包含 subset 字段。"""

    def _check() -> None:
        for row in rows:
            if not _row_subset_matches(row, subset):
                return
        _fail_plain(
            f"no row contains {dict(subset)!r}; actual={[dict(r) for r in rows]!r}"
        )

    _expect(_check)
