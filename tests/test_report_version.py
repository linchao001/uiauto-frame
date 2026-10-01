"""报告版本字段：由 AuthProvider.report_version_fields 提供。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pilot.account.auth import AuthProvider, register_auth_provider
from pilot.core.config import BrowserSettings, PilotConfig
from pilot.report.version import fill_report_version


class _VersionAuth(AuthProvider):
    def login(self, *, base_url: str, username: str, password: str) -> dict[str, Any]:
        raise AssertionError("not used")

    def token_store_items(self, login_data: dict[str, Any]) -> dict[str, str]:
        raise AssertionError("not used")

    def report_version_fields(self, config: PilotConfig) -> dict[str, str]:
        del config
        return {"product_version": "1.2.3", "serial_number": "SERIAL-001"}


def test_fill_report_version_writes_metadata(monkeypatch) -> None:
    cfg = PilotConfig(browser=BrowserSettings(base_url="https://device.example"))
    monkeypatch.setattr("pilot.pytest_plugin._load_pilot_config", lambda _config: cfg)
    meta: dict[str, str] = {"base_url": "https://device.example"}
    pytestconfig = SimpleNamespace(option=SimpleNamespace(htmlpath="reports/x/report.html"))
    register_auth_provider(pytestconfig, _VersionAuth())
    fill_report_version(meta, pytestconfig)
    assert meta["product_version"] == "1.2.3"
    assert meta["serial_number"] == "SERIAL-001"
    assert meta["base_url"] == "https://device.example"


def test_fill_report_version_skips_without_html() -> None:
    meta: dict[str, str] = {}
    fill_report_version(meta, SimpleNamespace(option=SimpleNamespace(htmlpath=None)))
    assert meta == {}


def test_fill_report_version_skips_when_provider_returns_empty(monkeypatch) -> None:
    cfg = PilotConfig(browser=BrowserSettings(base_url="https://device.example"))
    monkeypatch.setattr("pilot.pytest_plugin._load_pilot_config", lambda _config: cfg)
    meta: dict[str, str] = {"base_url": "https://device.example"}
    pytestconfig = SimpleNamespace(option=SimpleNamespace(htmlpath="reports/x/report.html"))
    # 未注册 → UnsetAuthProvider.report_version_fields → {}
    fill_report_version(meta, pytestconfig)
    assert meta == {"base_url": "https://device.example"}


def test_fill_report_version_swallows_provider_error(monkeypatch) -> None:
    class _Boom(AuthProvider):
        def login(self, *, base_url: str, username: str, password: str) -> dict[str, Any]:
            raise AssertionError("not used")

        def token_store_items(self, login_data: dict[str, Any]) -> dict[str, str]:
            raise AssertionError("not used")

        def report_version_fields(self, config: PilotConfig) -> dict[str, str]:
            raise RuntimeError("device down")

    cfg = PilotConfig(browser=BrowserSettings(base_url="https://device.example"))
    monkeypatch.setattr("pilot.pytest_plugin._load_pilot_config", lambda _config: cfg)
    meta: dict[str, str] = {"base_url": "https://device.example"}
    pytestconfig = SimpleNamespace(option=SimpleNamespace(htmlpath="reports/x/report.html"))
    register_auth_provider(pytestconfig, _Boom())
    fill_report_version(meta, pytestconfig)
    assert "product_version" not in meta
    assert meta["base_url"] == "https://device.example"


def test_apply_html_environment_fills_version_then_product_hook(monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest_metadata = pytest.importorskip("pytest_metadata")
    from pilot.pytest_plugin import _apply_html_environment

    metadata_key = pytest_metadata.plugin.metadata_key
    monkeypatch.setattr(
        "pilot.pytest_plugin._resolve_base_url",
        lambda _config: "https://device.example",
    )
    order: list[str] = []

    def _fill(metadata, config) -> None:
        del config
        order.append("version")
        metadata["product_version"] = "from-framework"

    monkeypatch.setattr("pilot.report.version.fill_report_version", _fill)
    seen: dict[str, dict[str, str]] = {}

    class _Hook:
        def pytest_pilot_report_metadata(self, metadata, config) -> None:
            del config
            order.append("hook")
            seen["before"] = dict(metadata)
            metadata["extra"] = "from-product"

    stash = {metadata_key: {"Python": "3.12", "Platform": "win"}}
    _apply_html_environment(
        SimpleNamespace(
            stash=stash,
            hook=_Hook(),
            option=SimpleNamespace(htmlpath="reports/x/report.html"),
        )
    )
    assert order == ["version", "hook"]
    assert "Python" not in stash[metadata_key]
    assert stash[metadata_key]["base_url"] == "https://device.example"
    assert stash[metadata_key]["product_version"] == "from-framework"
    assert stash[metadata_key]["extra"] == "from-product"
    assert seen["before"]["product_version"] == "from-framework"
