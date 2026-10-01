"""@pytest.mark.P0–P3 与 --priority CLI 过滤。"""

from __future__ import annotations

from typing import Any

import pytest

from pilot.core.priority_filter import (
    VALID_PRIORITIES,
    deselect_for_priority,
    marker_priority,
    normalize_priority,
    parse_priority_cli,
    should_run_for_priorities,
)


def _fake_item(*, marks: frozenset[str] | None = None) -> Any:
    """marks 为挂在用例上的标记名集合，如 frozenset({\"P0\"})。"""

    class _Marker:
        args: tuple[Any, ...] = ()
        kwargs: dict[str, Any] = {}

    class _Item:
        def get_closest_marker(self, name: str) -> _Marker | None:
            if marks is None or name not in marks:
                return None
            return _Marker()

    return _Item()


def test_valid_priorities_are_p0_to_p3() -> None:
    assert VALID_PRIORITIES == frozenset({"P0", "P1", "P2", "P3"})


def test_normalize_priority_uppercases() -> None:
    assert normalize_priority("p0") == "P0"
    assert normalize_priority("P1") == "P1"


def test_normalize_priority_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="P0"):
        normalize_priority("P9")
    with pytest.raises(ValueError, match="P0"):
        normalize_priority("")


def test_parse_priority_cli_comma_separated() -> None:
    assert parse_priority_cli("P0,P1") == frozenset({"P0", "P1"})
    assert parse_priority_cli(" p0 , p2 ") == frozenset({"P0", "P2"})


def test_parse_priority_cli_none_or_empty() -> None:
    assert parse_priority_cli(None) is None
    assert parse_priority_cli("") is None
    assert parse_priority_cli("  ") is None


def test_parse_priority_cli_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="P0"):
        parse_priority_cli("P0,PX")


def test_marker_priority_unmarked() -> None:
    assert marker_priority(_fake_item(marks=None)) is None
    assert marker_priority(_fake_item(marks=frozenset({"smoke"}))) is None


def test_marker_priority_reads_p_mark() -> None:
    assert marker_priority(_fake_item(marks=frozenset({"P0"}))) == "P0"
    assert marker_priority(_fake_item(marks=frozenset({"P3"}))) == "P3"


def test_marker_priority_rejects_multiple() -> None:
    with pytest.raises(ValueError, match="multiple"):
        marker_priority(_fake_item(marks=frozenset({"P0", "P1"})))


def test_unmarked_skipped_when_cli_filter_set() -> None:
    item = _fake_item(marks=None)
    assert should_run_for_priorities(item, frozenset({"P0"})) is False


def test_marked_kept_when_level_matches() -> None:
    item = _fake_item(marks=frozenset({"P0"}))
    assert should_run_for_priorities(item, frozenset({"P0", "P1"})) is True
    assert should_run_for_priorities(item, frozenset({"P2"})) is False


def test_deselect_for_priority() -> None:
    unmarked = _fake_item(marks=None)
    p0 = _fake_item(marks=frozenset({"P0"}))
    p2 = _fake_item(marks=frozenset({"P2"}))
    kept, deselected = deselect_for_priority([unmarked, p0, p2], frozenset({"P0"}))
    assert kept == [p0]
    assert deselected == [unmarked, p2]
