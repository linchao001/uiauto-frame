"""DB / 通用值断言：assertx.expect_*（不依赖真实库）。"""

from __future__ import annotations

import pytest

from pilot.core import assertx
from pilot.core.soft import soft_assertions


def test_expect_not_none_and_none() -> None:
    assertx.expect_not_none({"id": 1})
    assertx.expect_none(None)

    with pytest.raises(AssertionError):
        assertx.expect_not_none(None)
    with pytest.raises(AssertionError):
        assertx.expect_none({"id": 1})


def test_expect_row_subset_allow_extra() -> None:
    """默认 allow_extra=True：只校验关心的列。"""
    row = {"id": 1, "account": "a1", "display_name": "Alice", "extra": "x"}
    assertx.expect_row(row, {"account": "a1", "display_name": "Alice"})


def test_expect_row_rejects_mismatch() -> None:
    with pytest.raises(AssertionError, match="account"):
        assertx.expect_row({"account": "a1"}, {"account": "a2"})


def test_expect_row_disallow_extra() -> None:
    with pytest.raises(AssertionError, match="extra"):
        assertx.expect_row(
            {"account": "a1", "extra": "x"},
            {"account": "a1"},
            allow_extra=False,
        )


def test_expect_row_none_fails() -> None:
    with pytest.raises(AssertionError, match="None"):
        assertx.expect_row(None, {"account": "a1"})


def test_expect_rows_count_variants() -> None:
    rows = [{"id": 1}, {"id": 2}]
    assertx.expect_rows_count(rows, 2)
    assertx.expect_rows_count_at_least(rows, 1)
    assertx.expect_rows_count_at_most(rows, 10)
    with pytest.raises(AssertionError):
        assertx.expect_rows_count(rows, 3)


def test_expect_rows_equal_and_contain() -> None:
    rows = [
        {"account": "a", "display_name": "A", "noise": 1},
        {"account": "b", "display_name": "B", "noise": 2},
    ]
    assertx.expect_rows_equal(
        rows,
        [{"account": "a", "display_name": "A"}, {"account": "b", "display_name": "B"}],
    )
    assertx.expect_rows_contain(rows, {"account": "a", "display_name": "A"})
    assertx.expect_rows_contain(rows, {"account": "b"})
    with pytest.raises(AssertionError):
        assertx.expect_rows_contain(rows, {"account": "missing"})


def test_db_expect_soft_inside_context() -> None:
    """soft 作用域内 DB expect 失败继续执行并汇总。"""
    with pytest.raises(AssertionError) as excinfo:
        with soft_assertions():
            assertx.expect_not_none(None)
            assertx.expect_rows_count([], 1)
    message = str(excinfo.value)
    assert "2" in message
