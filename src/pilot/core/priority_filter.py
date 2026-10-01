"""@pytest.mark.P0–P3 与 --priority CLI：按优先级筛选用例。"""

from __future__ import annotations

import pytest

VALID_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})


def normalize_priority(raw: str) -> str:
    """规范化优先级字符串（供 CLI）；非法值抛 ValueError。"""
    level = str(raw).strip().upper()
    if level not in VALID_PRIORITIES:
        raise ValueError(
            f"invalid priority {raw!r}; expected one of {sorted(VALID_PRIORITIES)}"
        )
    return level


def parse_priority_cli(raw: str | None) -> frozenset[str] | None:
    """解析 ``--priority P0,P1``；空/None 表示不按优先级过滤。"""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return None
    return frozenset(normalize_priority(p) for p in parts)


def marker_priority(item: pytest.Item) -> str | None:
    """从 ``@pytest.mark.P0`` 等取出级别；无标记返回 None；多个优先级标记则报错。"""
    found = [level for level in sorted(VALID_PRIORITIES) if item.get_closest_marker(level)]
    if not found:
        return None
    if len(found) > 1:
        raise ValueError(
            "multiple priority marks on one case: "
            + ", ".join(f"@{m}" for m in found)
            + "; use exactly one of @pytest.mark.P0|P1|P2|P3"
        )
    return found[0]


def should_run_for_priorities(
    item: pytest.Item,
    allowed: frozenset[str],
) -> bool:
    """CLI 指定优先级时：仅保留级别命中的用例；未打标的剔除。"""
    level = marker_priority(item)
    if level is None:
        return False
    return level in allowed


def deselect_for_priority(
    items: list[pytest.Item],
    allowed: frozenset[str],
) -> tuple[list[pytest.Item], list[pytest.Item]]:
    """按允许的优先级拆成 (保留, 剔除)。"""
    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if should_run_for_priorities(item, allowed):
            kept.append(item)
        else:
            deselected.append(item)
    return kept, deselected
