"""SshSettings 与 load_config 对 ssh / auto_setup_remote 的解析。"""

from __future__ import annotations

from pathlib import Path

from pilot.core.config import DbSettings, SshSettings, load_config


def test_ssh_settings_enabled_when_user() -> None:
    assert SshSettings().enabled is False
    assert SshSettings(user="sshuser").enabled is True
    assert SshSettings(user="sshuser").configured is True


def test_db_auto_setup_remote_default() -> None:
    assert DbSettings(user="root", database="app").auto_setup_remote is True


def test_load_config_ssh_host_falls_back_to_db_then_base_url(tmp_path: Path) -> None:
    """ssh.host 省略：优先 db.host，再无则 base_url 主机。"""
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
  ssh:
    user: sshuser
    password: sshuser
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.ssh.enabled is True
    assert cfg.ssh.host == "192.168.1.10"  # 与 db.host（来自 base_url）一致
    assert cfg.ssh.user == "sshuser"
    assert cfg.ssh.port == 22
    assert cfg.db.auto_setup_remote is True
    assert "ssh" not in cfg.extras


def test_load_config_ssh_explicit_host(tmp_path: Path) -> None:
    cfg_file = tmp_path / "env.yaml"
    cfg_file.write_text(
        """
default:
  browser:
    base_url: http://192.168.1.10
  ssh:
    host: 10.0.0.9
    user: sshuser
    password: x
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.ssh.host == "10.0.0.9"
