"""DbSettings 与 load_config 对 db 块的解析。"""

from __future__ import annotations

from pathlib import Path

from pilot.core.config import DbSettings, load_config


def test_db_settings_enabled_when_user_or_database() -> None:
    assert DbSettings().enabled is False
    assert DbSettings(user="root").enabled is True
    assert DbSettings(database="app").enabled is True


def test_load_config_parses_db_and_host_fallback(tmp_path: Path) -> None:
    """未写 db.host 时回落 browser.base_url 主机。"""
    cfg_file = tmp_path / "env.yaml"
    cfg_file.write_text(
        """
default:
  browser:
    base_url: http://192.168.1.10:8080
  db:
    user: root
    password: secret
    database: app_db
    port: 3307
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.db.enabled is True
    assert cfg.db.host == "192.168.1.10"
    assert cfg.db.port == 3307
    assert cfg.db.user == "root"
    assert cfg.db.password == "secret"
    assert cfg.db.database == "app_db"
    assert cfg.db.charset == "utf8mb4"
    assert cfg.db.autocommit is True
    # db 不应再出现在 extras
    assert "db" not in cfg.extras


def test_load_config_without_db() -> None:
    cfg = load_config(None)
    assert cfg.db.enabled is False
