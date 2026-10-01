"""pytest 会话结束时收集统计并触发飞书通知。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pilot.notify.feishu import SessionSummary
from pilot.pytest_plugin import _collect_session_summary, _maybe_notify_feishu


def test_collect_session_summary_counts_and_failed_names() -> None:
    """从 terminalreporter.stats 汇总 passed/failed/skipped/error。"""
    failed_rep = SimpleNamespace(nodeid="tests/a.py::test_fail", when="call", failed=True)
    error_rep = SimpleNamespace(nodeid="tests/b.py::test_err", when="setup", failed=True)
    terminal = SimpleNamespace(
        stats={
            "passed": [object(), object()],
            "failed": [failed_rep],
            "skipped": [object()],
            "error": [error_rep],
        }
    )
    session = SimpleNamespace(
        config=SimpleNamespace(
            pluginmanager=SimpleNamespace(get_plugin=lambda name: terminal if name == "terminalreporter" else None)
        )
    )
    summary = _collect_session_summary(session, duration_sec=9.5)  # type: ignore[arg-type]
    assert summary == SessionSummary(
        passed=2,
        failed=1,
        skipped=1,
        error=1,
        duration_sec=9.5,
        failed_names=["tests/a.py::test_fail", "tests/b.py::test_err"],
    )


def test_maybe_notify_feishu_uses_pilot_config() -> None:
    """读 session 上的 pilot_config 并调用 notify。"""
    settings = MagicMock()
    settings.enabled = True
    config = MagicMock()
    config.feishu = settings
    config.env = "ci"
    session = MagicMock()
    session.config.stash = {}
    # 通过 fixture 缓存不好直接拿；用我们约定的 session.config._pilot_config 或 stash
    # 实际实现用 load from pytestconfig；此处测 hook 辅助函数入参
    summary = SessionSummary(passed=1, failed=0, skipped=0, error=0, duration_sec=1.0)
    with patch("pilot.pytest_plugin.notify_session_summary", return_value=True) as notify:
        _maybe_notify_feishu(config, summary)
    notify.assert_called_once_with(settings, summary, env="ci")


def test_maybe_notify_feishu_noop_when_disabled() -> None:
    settings = MagicMock()
    settings.enabled = False
    config = MagicMock()
    config.feishu = settings
    config.env = "local"
    summary = SessionSummary(passed=1, failed=0, skipped=0, error=0, duration_sec=1.0)
    with patch("pilot.pytest_plugin.notify_session_summary") as notify:
        _maybe_notify_feishu(config, summary)
    notify.assert_not_called()
