"""飞书群机器人：pytest 会话结束汇总通知。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from pilot.core.config import FeishuSettings
from pilot.core.logging import get_logger

logger = get_logger("pilot")


@dataclass(frozen=True)
class SessionSummary:
    """一次 pytest 会话的统计摘要。"""

    passed: int
    failed: int
    skipped: int
    error: int
    duration_sec: float
    failed_names: list[str] = field(default_factory=list)


def build_summary_text(
    summary: SessionSummary,
    *,
    include_failures: bool,
    failure_limit: int,
    env: str,
) -> str:
    """组装飞书 text 消息正文。"""
    total = summary.passed + summary.failed + summary.skipped + summary.error
    lines = [
        f"[Pilot] env={env} 会话结束",
        (
            f"total={total} passed={summary.passed} failed={summary.failed} "
            f"skipped={summary.skipped} error={summary.error}"
        ),
        f"duration={summary.duration_sec:.1f}s",
    ]
    if include_failures and summary.failed_names:
        limit = max(0, failure_limit)
        shown = summary.failed_names[:limit]
        lines.append("failures:")
        lines.extend(f"- {name}" for name in shown)
        remaining = len(summary.failed_names) - len(shown)
        if remaining > 0:
            lines.append(f"... +{remaining} more")
    return "\n".join(lines)


def _post_webhook(webhook: str, text: str, timeout_sec: float) -> bool:
    """向飞书机器人 Webhook POST text 消息；成功返回 True。"""
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        # 飞书成功时通常返回 code=0
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        code = data.get("code", data.get("StatusCode"))
        if code is not None and int(code) != 0:
            logger.warning("Feishu webhook rejected: %s", body[:200])
            return False
    return True


def notify_session_summary(
    settings: FeishuSettings,
    summary: SessionSummary,
    *,
    env: str = "local",
) -> bool:
    """按配置发送会话汇总；未启用或失败时返回 False，不向外抛异常。"""
    if not settings.enabled:
        return False
    text = build_summary_text(
        summary,
        include_failures=settings.include_failures,
        failure_limit=settings.failure_limit,
        env=env,
    )
    try:
        return _post_webhook(settings.webhook, text, settings.timeout_sec)
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Feishu notify failed: %s", exc)
        return False
