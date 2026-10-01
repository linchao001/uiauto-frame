"""用例元数据标记：``case_title`` 与优先级 ``P0``–``P3``。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from pilot.core.logging import get_logger
from pilot.core.priority_filter import VALID_PRIORITIES

logger = get_logger("pilot.report.case_marks")

CASE_TITLE_MARKER = "case_title"
PRIORITY_MARKERS = tuple(sorted(VALID_PRIORITIES))  # P0..P3
# 数值越小优先级越高
_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

MARKER_HELP = (
    (
        CASE_TITLE_MARKER,
        "case_title(case_id=..., title=...): case id and human-readable title for reports",
    ),
)


@dataclass(frozen=True)
class CaseMeta:
    """单条 pytest item 解析后的用例元数据。"""

    case_id: str = ""
    title: str = ""
    priority: str | None = None

    @property
    def any(self) -> bool:
        return bool(self.case_id or self.title or self.priority)


def register_case_markers(config: pytest.Config) -> None:
    """注册 ``case_title``（P0–P3 由插件其它处注册）。"""
    for name, help_text in MARKER_HELP:
        config.addinivalue_line("markers", f"{name}: {help_text}")


def parse_case_title(marker: Any) -> tuple[str, str]:
    """从 ``case_title`` mark 取出 ``(case_id, title)``。"""
    kwargs = getattr(marker, "kwargs", {}) or {}
    args = getattr(marker, "args", ()) or ()

    case_id = str(kwargs.get("case_id") or "").strip()
    title = str(kwargs.get("title") or "").strip()

    if not case_id and len(args) >= 1:
        case_id = str(args[0]).strip()
    if not title and len(args) >= 2:
        title = str(args[1]).strip()
    return case_id, title


def resolve_priority(item: pytest.Item, *, warn: bool = True) -> str | None:
    """取 item 上最高优先级；多枚并存时告警并保留最高（P0 > … > P3）。

    收集阶段仍由 ``marker_priority`` 硬失败拦截多标；此处偏报告兜底。
    """
    found = [name for name in PRIORITY_MARKERS if item.get_closest_marker(name) is not None]
    if not found:
        return None
    chosen = min(found, key=lambda n: _PRIORITY_RANK[n])
    if len(found) > 1 and warn:
        logger.warning(
            "multiple priority marks on %s: %s; using %s",
            getattr(item, "nodeid", item),
            ",".join(found),
            chosen,
        )
    return chosen


def parametrize_meta_data(item: pytest.Item) -> dict[str, Any]:
    """读行级 ``meta_data``（API 风格）或 ``@cases`` 的 ``case`` 对象。"""
    callspec = getattr(item, "callspec", None)
    if callspec is None:
        return {}
    params = getattr(callspec, "params", {}) or {}

    meta = params.get("meta_data")
    if isinstance(meta, dict):
        return dict(meta)

    # Pilot @cases：parametrize("case", Case(...))
    case = params.get("case")
    if case is None:
        return {}
    out: dict[str, Any] = {}
    case_id = getattr(case, "id", None)
    if case_id is not None and str(case_id).strip():
        out["id"] = str(case_id).strip()
    title = getattr(case, "title", None)
    if title is not None and str(title).strip():
        out["title"] = str(title).strip()
    priority = getattr(case, "priority", None)
    if priority is not None and str(priority).strip():
        out["priority"] = str(priority).strip()
    return out


def _case_meta_from_row(row: dict[str, Any]) -> CaseMeta:
    case_id = str(row.get("id") or row.get("case_id") or "").strip()
    title = str(row.get("title") or "").strip()
    priority_raw = str(row.get("priority") or "").strip().upper()
    priority = priority_raw if priority_raw in VALID_PRIORITIES else None
    return CaseMeta(case_id=case_id, title=title, priority=priority)


def _merge_priority(
    row_priority: str | None,
    mark_priority: str | None,
    *,
    item: pytest.Item,
    warn: bool,
) -> str | None:
    if row_priority and mark_priority and row_priority != mark_priority:
        chosen = min((row_priority, mark_priority), key=lambda p: _PRIORITY_RANK[p])
        if warn:
            logger.warning(
                "priority mismatch on %s: meta_data=%s vs marks=%s; using %s",
                getattr(item, "nodeid", item),
                row_priority,
                mark_priority,
                chosen,
            )
        return chosen
    return row_priority or mark_priority


def resolve_case_meta(item: pytest.Item, *, warn: bool = True) -> CaseMeta:
    """合并行级数据与 ``case_title`` / P0–P3；行级覆盖 id/title。"""
    mark_case_id = ""
    mark_title = ""
    marker = item.get_closest_marker(CASE_TITLE_MARKER)
    if marker is not None:
        mark_case_id, mark_title = parse_case_title(marker)
    mark_priority = resolve_priority(item, warn=warn)

    row = parametrize_meta_data(item)
    if not row:
        return CaseMeta(case_id=mark_case_id, title=mark_title, priority=mark_priority)

    row_meta = _case_meta_from_row(row)
    case_id = row_meta.case_id or mark_case_id
    title = row_meta.title or mark_title
    priority = _merge_priority(row_meta.priority, mark_priority, item=item, warn=warn)

    if warn and row_meta.title and mark_title and row_meta.title != mark_title:
        logger.warning(
            "case title mismatch on %s: meta_data.title=%r vs case_title=%r; using meta_data",
            getattr(item, "nodeid", item),
            row_meta.title,
            mark_title,
        )

    return CaseMeta(case_id=case_id, title=title, priority=priority)


def format_case_summary(meta: CaseMeta) -> str:
    """一行摘要，如 ``UI-01 [P0] 登录…``。"""
    parts: list[str] = []
    if meta.case_id:
        parts.append(meta.case_id)
    if meta.priority:
        parts.append(f"[{meta.priority}]")
    if meta.title:
        parts.append(meta.title)
    return " ".join(parts)


def user_properties_for_meta(meta: CaseMeta) -> list[tuple[str, str]]:
    """把 CaseMeta 写成 pytest ``user_properties``。"""
    props: list[tuple[str, str]] = []
    if meta.case_id:
        props.append(("case_id", meta.case_id))
    if meta.title:
        props.append(("title", meta.title))
    if meta.priority:
        props.append(("priority", meta.priority))
    return props
