"""FeishuSettings 与 load_config 对 feishu 块的解析。"""

from __future__ import annotations

from pathlib import Path

from pilot.core.config import FeishuSettings, load_config


def test_feishu_settings_enabled_requires_flag_and_webhook() -> None:
    """仅 enabled=true 且 webhook 非空时视为启用。"""
    assert FeishuSettings().enabled is False
    assert FeishuSettings(enabled=True).enabled is False
    assert FeishuSettings(webhook="https://example.com/hook").enabled is False
    assert FeishuSettings(enabled=True, webhook="https://example.com/hook").enabled is True


def test_load_config_parses_feishu(tmp_path: Path) -> None:
    """解析 YAML feishu 块，且不进入 extras。"""
    cfg_file = tmp_path / "env.yaml"
    cfg_file.write_text(
        """
default:
  feishu:
    enabled: true
    webhook: https://open.feishu.cn/open-apis/bot/v2/hook/abc
    include_failures: true
    failure_limit: 10
    timeout_sec: 3
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.feishu.enabled is True
    assert cfg.feishu.webhook == "https://open.feishu.cn/open-apis/bot/v2/hook/abc"
    assert cfg.feishu.include_failures is True
    assert cfg.feishu.failure_limit == 10
    assert cfg.feishu.timeout_sec == 3.0
    assert "feishu" not in cfg.extras


def test_load_config_without_feishu() -> None:
    cfg = load_config(None)
    assert cfg.feishu.enabled is False
    assert cfg.feishu.include_failures is False
    assert cfg.feishu.failure_limit == 20
