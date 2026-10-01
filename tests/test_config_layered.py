"""分层配置：product.yaml + env/<device>.yaml。"""

from __future__ import annotations

from pathlib import Path

import pytest

from pilot.core.config import discover_envs, load_config, resolve_env_name


def _write_layered(tmp_path: Path) -> Path:
    """写入示例分层 config 目录。"""
    config = tmp_path / "config"
    env_dir = config / "env"
    env_dir.mkdir(parents=True)
    (config / "product.yaml").write_text(
        """
product: demo
env: lab-a
browser:
  headless: true
  timeout_ms: 5000
accounts:
  buyer:
    username: shared
    password: shared
""",
        encoding="utf-8",
    )
    (env_dir / "lab-a.yaml").write_text(
        """
browser:
  base_url: https://lab-a.example
ssh:
  user: sshuser
  password: changeme
db:
  user: dbuser
  password: changeme
  database: app
vars:
  device: lab-a
""",
        encoding="utf-8",
    )
    (env_dir / "lab-b.yaml").write_text(
        """
browser:
  base_url: https://lab-b.example
  headless: false
ssh:
  user: other
  password: changeme
db:
  user: dbuser
  password: changeme
  database: app
vars:
  device: lab-b
""",
        encoding="utf-8",
    )
    return config


def test_discover_envs(tmp_path: Path) -> None:
    config = _write_layered(tmp_path)
    assert discover_envs(config) == ["lab-a", "lab-b"]


def test_resolve_env_name_priority() -> None:
    available = ["lab-a", "lab-b"]
    assert resolve_env_name(explicit="lab-b", configured="lab-a", available=available) == (
        "lab-b"
    )
    assert resolve_env_name(explicit=None, configured="lab-a", available=available) == (
        "lab-a"
    )
    assert resolve_env_name(explicit=None, configured=None, available=["only"]) == "only"
    with pytest.raises(FileNotFoundError, match="Unknown env"):
        resolve_env_name(explicit="missing", available=available)


def test_load_config_layered_uses_product_default_env(tmp_path: Path) -> None:
    config = _write_layered(tmp_path)
    cfg = load_config(config_dir=config)
    assert cfg.env == "lab-a"
    assert cfg.browser.base_url == "https://lab-a.example"
    assert cfg.browser.headless is True
    assert cfg.browser.timeout_ms == 5000
    assert cfg.ssh.user == "sshuser"
    assert cfg.db.host == "lab-a.example"
    assert cfg.accounts["buyer"]["username"] == "shared"
    assert cfg.extras.get("vars", {}).get("device") == "lab-a"
    # 未配置时 default_account 为空，由产品自定
    assert cfg.default_account == ""


def test_load_config_default_account_from_product(tmp_path: Path) -> None:
    """product.yaml 可显式指定 default_account。"""
    config = _write_layered(tmp_path)
    product = (config / "product.yaml").read_text(encoding="utf-8")
    (config / "product.yaml").write_text(
        product + "\ndefault_account: buyer\n",
        encoding="utf-8",
    )
    cfg = load_config(config_dir=config)
    assert cfg.default_account == "buyer"
    assert "default_account" not in cfg.extras


def test_load_config_unknown_vendor_block_goes_to_extras(tmp_path: Path) -> None:
    """框架不认识的顶层键进入 extras，供产品自用（不解析其字段）。"""
    config = _write_layered(tmp_path)
    env_a = config / "env" / "lab-a.yaml"
    text = env_a.read_text(encoding="utf-8")
    env_a.write_text(
        text
        + """
vendor_ext:
  endpoint: /v1/session
""",
        encoding="utf-8",
    )
    cfg = load_config(config_dir=config)
    assert cfg.extras.get("vendor_ext", {}).get("endpoint") == "/v1/session"


def test_load_config_layered_explicit_env(tmp_path: Path) -> None:
    config = _write_layered(tmp_path)
    cfg = load_config(config_dir=config, env="lab-b")
    assert cfg.env == "lab-b"
    assert cfg.browser.base_url == "https://lab-b.example"
    assert cfg.browser.headless is False
    assert cfg.ssh.user == "other"


def test_load_config_path_directory_is_config_dir(tmp_path: Path) -> None:
    """path 指向目录时按分层配置加载。"""
    config = _write_layered(tmp_path)
    cfg = load_config(config, env="lab-b")
    assert cfg.env == "lab-b"
    assert cfg.browser.base_url == "https://lab-b.example"


def test_load_config_legacy_single_file_still_works(tmp_path: Path) -> None:
    """单文件 env.yaml（default + 命名块）保持兼容。"""
    cfg_file = tmp_path / "env.yaml"
    cfg_file.write_text(
        """
default:
  browser:
    headless: true
    timeout_ms: 1000
staging:
  browser:
    base_url: https://staging.example
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file, env="staging")
    assert cfg.env == "staging"
    assert cfg.browser.base_url == "https://staging.example"
    assert cfg.browser.headless is True
