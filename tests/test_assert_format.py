"""断言失败 diff 表格格式。"""

from __future__ import annotations

import logging

import pytest

from pilot.core import assertx
from pilot.core.assert_format import format_assertion_failure, format_plain_failure
from pilot.core.soft import soft_assertions


def test_format_assertion_failure_table() -> None:
    """可解析的 expected/got 行排成 Field / Expected / Actual 表。"""
    text = format_assertion_failure(
        "row mismatch",
        ["account: expected 'a2', got 'a1'", "display_name: expected 'Bob', got 'Alice'"],
    )
    assert "Assertion failed: row mismatch (2 differences)" in text
    assert "Field" in text and "Expected" in text and "Actual" in text
    assert "account" in text
    assert "'a2'" in text and "'a1'" in text
    assert "'Bob'" in text and "'Alice'" in text


def test_format_plain_and_unparsed_bullets() -> None:
    """无法解析的 diff 用 bullet；plain 包装单行失败。"""
    bullets = format_assertion_failure("row mismatch", ["missing key 'id'"])
    assert "Assertion failed: row mismatch" in bullets
    assert "• missing key 'id'" in bullets

    plain = format_plain_failure("expected value to be not None")
    assert "Assertion failed" in plain
    assert "• expected value to be not None" in plain


def test_summarize_playwright_value_mismatch() -> None:
    """Playwright to_have_value 失败压成期望/实际两行。"""
    from pilot.core.assert_format import summarize_failure_message

    msg = (
        "Locator expected to have Value '__demo_fail_wrong_expect__'\n"
        "Actual value: 12345 \n"
        "Call log:\n"
        "  - Expect \"to_have_value\" with timeout 15000ms\n"
        "screenshot: test-results/x.png"
    )
    summary = summarize_failure_message(msg)
    assert "期望: __demo_fail_wrong_expect__" in summary
    assert "实际: 12345" in summary
    assert "Call log" not in summary
    assert "screenshot" not in summary


def test_wrap_ui_assertion_failure_with_message() -> None:
    """UI 失败包装：业务提示 + 原因归类 + 期望/实际。"""
    from pilot.core.assert_format import wrap_ui_assertion_failure

    raw = AssertionError(
        "Locator expected to have Value 'abc'\n"
        "Actual value: 12345\n"
        "Call log:\n"
        "  - Expect \"to_have_value\""
    )
    wrapped = wrap_ui_assertion_failure(raw, message="电话栏当前值不正确")
    text = str(wrapped)
    assert text.startswith("断言失败: 电话栏当前值不正确")
    assert "原因: 元素值不正确" in text
    assert "期望: abc" in text
    assert "实际: 12345" in text
    assert "Call log" not in text


def test_classify_not_found() -> None:
    from pilot.core.assert_format import classify_ui_failure

    msg = (
        "Locator expected to be visible\n"
        "Actual value: None\n"
        "Error: element(s) not found"
    )
    assert classify_ui_failure(msg) == "元素未找到"


def test_expect_row_mismatch_message_is_diff_table() -> None:
    """expect_row 字段不匹配时抛出表格化失败信息。"""
    with pytest.raises(AssertionError) as excinfo:
        assertx.expect_row({"account": "a1"}, {"account": "a2"})
    msg = str(excinfo.value)
    assert "Assertion failed" in msg
    assert "Field" in msg and "Expected" in msg and "Actual" in msg
    assert "account" in msg
    assert "'a2'" in msg and "'a1'" in msg


def test_expect_row_mismatch_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    """值断言失败时同步打 error 日志（含同一段 diff）。"""
    with caplog.at_level(logging.ERROR, logger="pilot"):
        with pytest.raises(AssertionError):
            assertx.expect_row({"account": "a1"}, {"account": "a2"})
    assert any("Assertion failed" in r.message for r in caplog.records)


def test_soft_aggregates_each_failure_as_diff_block() -> None:
    """软断言汇总：每条失败各自一块 diff 表，而不是单行拼接。"""
    with pytest.raises(AssertionError) as excinfo:
        with soft_assertions():
            assertx.expect_row({"account": "a1"}, {"account": "a2"})
            assertx.expect_not_none(None)
    message = str(excinfo.value)
    assert "Soft assertion failures (2)" in message
    assert "Assertion failed" in message
    assert "Field" in message and "Expected" in message
    assert "account" in message
    assert "not None" in message or "None" in message
    # 两条失败应各自编号
    assert "[1]" in message and "[2]" in message
