"""device marker 与 env 过滤。"""

from __future__ import annotations

from typing import Any

from pilot.core.device_filter import deselect_for_env, marker_devices, should_run_on_env


def _fake_item(*, device_args: tuple[Any, ...] | None) -> Any:
    class _Marker:
        def __init__(self, args: tuple[Any, ...]) -> None:
            self.args = args
            self.kwargs: dict[str, Any] = {}

    class _Item:
        def get_closest_marker(self, name: str) -> _Marker | None:
            if name != "device" or device_args is None:
                return None
            return _Marker(device_args)

    return _Item()


def test_unmarked_runs_on_any_env() -> None:
    item = _fake_item(device_args=None)
    assert marker_devices(item) is None
    assert should_run_on_env(item, "lab-a") is True


def test_marked_only_listed_envs() -> None:
    item = _fake_item(device_args=("lab-a",))
    assert marker_devices(item) == frozenset({"lab-a"})
    assert should_run_on_env(item, "lab-a") is True
    assert should_run_on_env(item, "lab-b") is False


def test_deselect_for_env() -> None:
    keep = _fake_item(device_args=None)
    only_a = _fake_item(device_args=("lab-a",))
    only_b = _fake_item(device_args=("lab-b",))
    kept, deselected = deselect_for_env([keep, only_a, only_b], "lab-a")
    assert kept == [keep, only_a]
    assert deselected == [only_b]
