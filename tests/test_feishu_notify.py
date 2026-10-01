"""飞书会话汇总通知：组文案与发送。"""

from __future__ import annotations

from unittest.mock import patch

from pilot.core.config import FeishuSettings
from pilot.notify.feishu import SessionSummary, build_summary_text, notify_session_summary


def test_build_summary_text_concise() -> None:
    text = build_summary_text(
        SessionSummary(
            passed=8,
            failed=1,
            skipped=1,
            error=0,
            duration_sec=12.5,
            failed_names=["tests/test_a.py::test_x"],
        ),
        include_failures=False,
        failure_limit=20,
        env="staging",
    )
    assert "Pilot" in text
    assert "staging" in text
    assert "passed=8" in text
    assert "failed=1" in text
    assert "skipped=1" in text
    assert "12.5" in text
    assert "test_x" not in text


def test_build_summary_text_includes_failures_with_limit() -> None:
    names = [f"test_{i}" for i in range(5)]
    text = build_summary_text(
        SessionSummary(
            passed=0,
            failed=5,
            skipped=0,
            error=0,
            duration_sec=1.0,
            failed_names=names,
        ),
        include_failures=True,
        failure_limit=2,
        env="local",
    )
    assert "test_0" in text
    assert "test_1" in text
    assert "test_2" not in text
    assert "+3 more" in text


def test_notify_skipped_when_disabled() -> None:
    settings = FeishuSettings(enabled=False, webhook="https://example.com/hook")
    with patch("pilot.notify.feishu._post_webhook") as post:
        ok = notify_session_summary(
            settings,
            SessionSummary(passed=1, failed=0, skipped=0, error=0, duration_sec=1.0),
        )
    assert ok is False
    post.assert_not_called()


def test_notify_posts_when_enabled() -> None:
    settings = FeishuSettings(
        enabled=True,
        webhook="https://example.com/hook",
        include_failures=True,
        failure_limit=5,
        timeout_sec=3,
    )
    summary = SessionSummary(
        passed=2,
        failed=1,
        skipped=0,
        error=0,
        duration_sec=4.0,
        failed_names=["test_boom"],
    )
    with patch("pilot.notify.feishu._post_webhook", return_value=True) as post:
        ok = notify_session_summary(settings, summary, env="ci")
    assert ok is True
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == settings.webhook
    assert "test_boom" in args[1]
    assert kwargs.get("timeout_sec", args[2] if len(args) > 2 else None) == 3


def test_notify_network_error_returns_false_no_raise() -> None:
    settings = FeishuSettings(enabled=True, webhook="https://example.com/hook")
    with patch("pilot.notify.feishu._post_webhook", side_effect=OSError("down")):
        ok = notify_session_summary(
            settings,
            SessionSummary(passed=0, failed=1, skipped=0, error=0, duration_sec=1.0),
        )
    assert ok is False
