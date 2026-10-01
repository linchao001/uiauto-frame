from pathlib import Path

from pilot.core.config import load_config


def test_load_config_merges_env_override(tmp_path: Path):
    cfg_file = tmp_path / "env.yaml"
    cfg_file.write_text(
        """
default:
  browser:
    headless: true
    timeout_ms: 1000
    channel: chrome
  accounts:
    buyer:
      username: buyer
      password: x
staging:
  browser:
    headless: false
    base_url: https://staging.example
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file, env="staging")
    assert cfg.env == "staging"
    assert cfg.browser.headless is False
    assert cfg.browser.base_url == "https://staging.example"
    assert cfg.browser.channel == "chrome"
    assert cfg.accounts["buyer"]["username"] == "buyer"
