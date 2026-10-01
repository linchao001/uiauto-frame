"""BaseFlow.open_as：经 AuthProvider 接口登录后打开页面 URL。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from pilot.account.auth import AuthProvider
from pilot.core.config import BrowserSettings, PilotConfig
from pilot.flow.base import BaseFlow


class _FakeAuth(AuthProvider):
    def __init__(self) -> None:
        self.login_calls: list[tuple[str, str, str]] = []

    def login(self, *, base_url: str, username: str, password: str) -> dict[str, Any]:
        self.login_calls.append((base_url, username, password))
        return {"raw": "login"}

    def token_store_items(self, login_data: dict[str, Any]) -> dict[str, str]:
        return {"session": str(login_data["raw"])}


def _flow(*, auth: AuthProvider | None = None) -> BaseFlow:
    page = MagicMock()
    page.context = MagicMock()
    config = PilotConfig(
        browser=BrowserSettings(base_url="https://app.example"),
        accounts={"test_user": {"username": "u1", "password": "secret"}},
    )
    return BaseFlow(page, config, auth=auth)


def test_open_as_installs_token_and_opens_page(monkeypatch) -> None:
    """账号角色接口登录后注入 token，再打开传入的页面 URL。"""
    auth = _FakeAuth()
    flow = _flow(auth=auth)
    installed: dict = {}

    def _install(context, items):
        installed["context"] = context
        installed["items"] = items

    monkeypatch.setattr("pilot.flow.base.install_local_storage", _install)

    flow.open_as("test_user", "/home")

    assert auth.login_calls == [("https://app.example", "u1", "secret")]
    assert installed["context"] is flow.page.context
    assert installed["items"] == {"session": "login"}
    flow.page.goto.assert_called_once_with(
        "https://app.example/home",
        wait_until="domcontentloaded",
    )


def test_open_as_requires_auth_provider() -> None:
    flow = _flow(auth=None)
    with __import__("pytest").raises(RuntimeError, match="AuthProvider"):
        flow.open_as("test_user", "/home")
