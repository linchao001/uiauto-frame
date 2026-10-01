"""断言失败可读格式：diff-first 表格（无 HTTP 上下文）。"""

from __future__ import annotations

import re
from dataclasses import dataclass


# 解析「path: expected X, got Y」类 diff 行，便于排成表格
_DIFF_EXPECT_GOT = re.compile(
    r"^(?P<path>[^:]+): expected (?P<expected>.+), got (?P<actual>.+)$"
)


@dataclass(frozen=True)
class _DiffRow:
    field: str
    expected: str
    actual: str


def _parse_diff_line(line: str) -> _DiffRow | None:
    """能解析则返回表格行，否则 None（走 bullet 回退）。"""
    match = _DIFF_EXPECT_GOT.match(line.strip())
    if not match:
        return None
    return _DiffRow(match.group("path"), match.group("expected"), match.group("actual"))


def _format_table(rows: list[_DiffRow]) -> str:
    field_w = max(len("Field"), *(len(r.field) for r in rows))
    exp_w = max(len("Expected"), *(len(r.expected) for r in rows))
    act_w = max(len("Actual"), *(len(r.actual) for r in rows))
    header = f"  {'Field'.ljust(field_w)}  {'Expected'.ljust(exp_w)}  Actual"
    sep = f"  {'-' * field_w}  {'-' * exp_w}  {'-' * act_w}"
    body = [
        f"  {r.field.ljust(field_w)}  {r.expected.ljust(exp_w)}  {r.actual}"
        for r in rows
    ]
    return "\n".join([header, sep, *body])


def format_assertion_failure(label: str, diffs: list[str]) -> str:
    """把结构化 diff 列表排成紧凑失败消息（终端 / pytest / 日志共用）。"""
    lines: list[str] = []
    if len(diffs) > 1:
        lines.append(f"Assertion failed: {label} ({len(diffs)} differences)")
    else:
        lines.append(f"Assertion failed: {label}")

    bar_len = min(72, max(40, len(lines[0]) + 8))
    lines.append("─" * bar_len)

    if diffs:
        parsed = [_parse_diff_line(item) for item in diffs]
        if parsed and all(row is not None for row in parsed):
            lines.append(_format_table([row for row in parsed if row is not None]))
        else:
            for item in diffs:
                lines.append(f"  • {item}")

    return "\n".join(lines)


def format_plain_failure(message: str) -> str:
    """无结构化 diff 时的单行失败包装。"""
    return "\n".join(["Assertion failed", "─" * 40, f"  • {message}"])


# Playwright expect 常见模式：抽取期望/实际，去掉 Call log / Aria 噪音
_PW_EXPECTED_VALUE = re.compile(
    r"Locator expected to have Value\s+(?P<exp>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_PW_ACTUAL_VALUE = re.compile(
    r"^Actual value:\s*(?P<act>.*?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_PW_EXPECTED_GENERIC = re.compile(
    r"Locator expected to (?P<exp>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def summarize_failure_message(message: str) -> str:
    """把断言异常文案压成可读原因（期望/实际优先），供日志与报告步骤区使用。"""
    raw = (message or "").strip()
    if not raw:
        return "（无失败详情）"

    # 已是框架包装：抽取「原因 / 期望 / 实际」
    if raw.startswith("断言失败:") or raw.startswith("步骤失败:"):
        reason_line = ""
        expect_line = ""
        actual_line = ""
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("原因:"):
                reason_line = s
            elif s.startswith("期望:"):
                expect_line = s
            elif s.startswith("实际:"):
                actual_line = s
        picked = [x for x in (reason_line, expect_line, actual_line) if x]
        if picked:
            return "\n".join(picked)
        rest = "\n".join(raw.splitlines()[1:]).strip()
        if rest:
            return summarize_failure_message(rest)

    # 去掉截图行与冗长 Call log / Aria snapshot
    kept: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("screenshot:"):
            break
        if s.startswith("Call log:") or s.startswith("Aria snapshot:"):
            break
        kept.append(s)
    body = "\n".join(kept) if kept else raw

    exp_m = _PW_EXPECTED_VALUE.search(body)
    act_m = _PW_ACTUAL_VALUE.search(body)
    if exp_m and act_m:
        return (
            f"期望: {_strip_quotes(exp_m.group('exp'))}\n"
            f"实际: {_strip_quotes(act_m.group('act'))}"
        )

    gen_m = _PW_EXPECTED_GENERIC.search(body)
    if gen_m and act_m:
        return (
            f"期望: {_strip_quotes(gen_m.group('exp'))}\n"
            f"实际: {_strip_quotes(act_m.group('act'))}"
        )

    # 结构化 assertx 文案：保留前几行即可
    lines = [ln for ln in body.splitlines() if ln.strip()]
    return "\n".join(lines[:6]) if lines else "（无失败详情）"


def build_step_failure_message(step_name: str, error: BaseException) -> str:
    """用例步骤失败时的标准文案：步骤名 + 原因摘要 + 截图路径（若有）。"""
    original = str(error)
    reason = summarize_failure_message(original)
    parts = [f"步骤失败: {step_name}", reason]
    for line in original.splitlines():
        if line.strip().startswith("screenshot:"):
            parts.append(line.strip())
            break
    return "\n".join(parts)


def classify_ui_failure(message: str) -> str:
    """把 Playwright / UI 断言原文归类成简短原因（元素未找到、值不正确等）。"""
    text = message or ""
    lower = text.lower()

    if "element(s) not found" in lower:
        return "元素未找到"
    if "expected to be visible" in lower:
        if "actual value: none" in lower or "not found" in lower:
            return "元素未找到或不可见"
        return "元素不可见"
    if "expected to be hidden" in lower:
        return "元素仍可见（期望已隐藏）"
    if "expected to have value" in lower or "to_have_value" in lower:
        return "元素值不正确"
    if "expected to have text" in lower or "to_have_text" in lower:
        return "元素文本不正确"
    if "expected to have attribute" in lower or "to_have_attribute" in lower:
        return "元素属性不正确"
    if "expected to have count" in lower or "to_have_count" in lower:
        return "元素数量不正确"
    if "expected to have url" in lower or "to_have_url" in lower:
        return "页面 URL 不正确"
    if "timeout" in lower:
        return "等待超时"
    return "断言未通过"


def wrap_ui_assertion_failure(
    error: AssertionError,
    *,
    message: str | None = None,
) -> AssertionError:
    """为 UI 断言失败加上业务提示 + 原因归类 + 期望/实际摘要。"""
    raw = str(error).rstrip()
    if raw.startswith("断言失败:"):
        return error

    reason_type = classify_ui_failure(raw)
    detail = summarize_failure_message(raw)
    parts: list[str] = [
        f"断言失败: {message.strip()}" if message and message.strip() else f"断言失败: {reason_type}",
        f"原因: {reason_type}",
    ]
    # detail 已含期望/实际或压缩后的原文要点
    if detail and detail not in ("（无失败详情）", reason_type):
        # 避免与「原因:」完全重复
        if detail != f"原因: {reason_type}":
            parts.append(detail)
    for line in raw.splitlines():
        if line.strip().startswith("screenshot:"):
            parts.append(line.strip())
            break
    return AssertionError("\n".join(parts))
