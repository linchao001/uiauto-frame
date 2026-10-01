"""可选 pytest-html extras / 步骤记录（导入时不硬依赖 pytest-html）。"""

from __future__ import annotations

import html
from contextlib import contextmanager
from typing import Any, Iterator

from pilot.report.capture import get_test_item


def _queue_extra(extra: dict[str, Any]) -> None:
    item = get_test_item()
    if item is None:
        return
    extras = getattr(item, "_pilot_html_extras", None)
    if extras is None:
        extras = []
        item._pilot_html_extras = extras  # type: ignore[attr-defined]
    extras.append(extra)


def _make_extra(*, kind: str, content: str, name: str = "") -> dict[str, Any] | None:
    try:
        from pytest_html import extras
    except ImportError:
        return None
    if kind == "html":
        return extras.html(content)
    if kind == "json":
        return extras.json(content, name=name or "json")
    return extras.text(content, name=name or "Text")


def pop_html_extras(item: Any) -> list[dict[str, Any]]:
    """取出并清空 item 上排队的 extras。"""
    extras = getattr(item, "_pilot_html_extras", None) or []
    item._pilot_html_extras = []  # type: ignore[attr-defined]
    return list(extras)


def pop_steps(item: Any) -> list[tuple[str, str, str]]:
    """取出并清空已记录的 ``(title, status, detail)`` 步骤。"""
    steps = getattr(item, "_pilot_steps", None) or []
    item._pilot_steps = []  # type: ignore[attr-defined]
    # 兼容旧二元组 (title, status)
    normalized: list[tuple[str, str, str]] = []
    for entry in steps:
        if len(entry) >= 3:
            normalized.append((str(entry[0]), str(entry[1]), str(entry[2] or "")))
        else:
            normalized.append((str(entry[0]), str(entry[1]), ""))
    return normalized


def record_step(title: str, status: str, detail: str = "") -> None:
    """向当前 item 追加一步；失败时可带 ``detail``（原因摘要）。无绑定 item 时静默跳过。"""
    item = get_test_item()
    if item is None:
        return
    steps = getattr(item, "_pilot_steps", None)
    if steps is None:
        steps = []
        item._pilot_steps = steps  # type: ignore[attr-defined]
    steps.append((title, status, detail or ""))


@contextmanager
def step(title: str) -> Iterator[None]:
    """记录命名步骤到 HTML 报告（展开详情 / Title 悬停可见）。"""
    try:
        yield
    except BaseException as exc:
        from pilot.core.assert_format import summarize_failure_message

        detail = summarize_failure_message(str(exc)) if isinstance(exc, Exception) else ""
        record_step(title, "fail", detail)
        raise
    else:
        record_step(title, "ok")


def attach_text(body: str, name: str = "attachment") -> None:
    """把纯文本挂到当前用例的 HTML extras。"""
    extra = _make_extra(kind="text", content=body, name=name)
    if extra is not None:
        _queue_extra(extra)


def extras_for_text(body: str, name: str = "attachment") -> list[dict[str, Any]]:
    """构造文本 extra，不依赖当前 item。"""
    extra = _make_extra(kind="text", content=body, name=name)
    return [extra] if extra is not None else []


def extras_for_html(content: str) -> list[dict[str, Any]]:
    """构造内联 HTML extra。"""
    extra = _make_extra(kind="html", content=content)
    return [extra] if extra is not None else []


_STEP_ICON = {"ok": "✔", "fail": "✖"}


def render_case_detail_html(
    *,
    case_id: str = "",
    title: str = "",
    priority: str | None = None,
    steps: list[tuple[str, str]] | list[tuple[str, str, str]] | None = None,
) -> str:
    """用例元数据 + 步骤的转义 HTML（详情区 / 悬停浮层）；失败步骤附原因。"""
    # class 与 report.css / report.js 中的 pilot-* 选择器对齐
    parts: list[str] = ['<div class="pilot-case-detail">']
    head: list[str] = []
    if case_id:
        head.append(f"<strong>{html.escape(case_id)}</strong>")
    if priority:
        head.append(f"<span>[{html.escape(priority)}]</span>")
    if title:
        head.append(html.escape(title))
    if head:
        parts.append(f'<div class="pilot-case-title">{" ".join(head)}</div>')
    if steps:
        parts.append('<ol class="pilot-steps">')
        for entry in steps:
            step_title = entry[0]
            status = entry[1]
            detail = entry[2] if len(entry) >= 3 else ""
            icon = _STEP_ICON.get(status, "•")
            li_class = ' class="is-fail"' if status == "fail" else ""
            parts.append(
                f"<li{li_class}>{html.escape(icon)} {html.escape(step_title)}"
            )
            if status == "fail" and detail:
                # 原因单独一块，报告里一眼看到期望/实际
                reason_html = html.escape(detail).replace("\n", "<br/>")
                parts.append(
                    f'<div class="pilot-step-reason">{reason_html}</div>'
                )
            parts.append("</li>")
        parts.append("</ol>")
    parts.append("</div>")
    return "".join(parts)


def render_title_cell_html(*, title: str, detail_html: str = "") -> str:
    """Title 列单元格；有详情时带悬停浮层。"""
    label = html.escape(title) if title.strip() else ""
    detail = (detail_html or "").strip()
    if not detail:
        return f'<td class="col-caseTitle">{label}</td>'
    trigger = label or "详情"
    return (
        '<td class="col-caseTitle">'
        f'<span class="pilot-title-trigger" tabindex="0">{trigger}</span>'
        f'<div class="pilot-title-popup" role="tooltip">{detail}</div>'
        "</td>"
    )
