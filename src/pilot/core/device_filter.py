"""@pytest.mark.device 过滤：仅在匹配的 --env / --pilot-env 下收集用例。"""

from __future__ import annotations

import pytest


DEVICE_MARKER = "device"


def marker_devices(item: pytest.Item) -> frozenset[str] | None:
    """从 ``@pytest.mark.device(...)`` 取出允许的 env 名；无标记则返回 None。"""
    marker = item.get_closest_marker(DEVICE_MARKER)
    if marker is None:
        return None
    names = [str(a).strip() for a in marker.args if str(a).strip()]
    names.extend(str(v).strip() for v in marker.kwargs.values() if str(v).strip())
    return frozenset(names)


def should_run_on_env(item: pytest.Item, env: str) -> bool:
    """无 device 标记的用例在所有 env 执行；有标记则仅列出的 env。"""
    allowed = marker_devices(item)
    if allowed is None:
        return True
    return env in allowed


def deselect_for_env(
    items: list[pytest.Item],
    env: str,
) -> tuple[list[pytest.Item], list[pytest.Item]]:
    """按当前 env 拆成 (保留, 剔除)。"""
    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if should_run_on_env(item, env):
            kept.append(item)
        else:
            deselected.append(item)
    return kept, deselected
