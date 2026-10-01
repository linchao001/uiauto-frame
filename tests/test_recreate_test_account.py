"""会话开始：调用 AuthProvider.recreate_test_account。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from pilot.account.auth import AuthProvider
from pilot.core.config import BrowserSettings, PilotConfig


class _RecreateAuth(AuthProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    def login(self, *, base_url: str, username: str, password: str) -> dict[str, Any]:
        raise AssertionError("not used")

    def token_store_items(self, login_data: dict[str, Any]) -> dict[str, str]:
        raise AssertionError("not used")

    def recreate_test_account(self, config: PilotConfig, db: Any) -> None:
        self.calls.append((config, db))


def test_recreate_hook_invokes_provider() -> None:
    """产品覆盖 recreate_test_account 时应被会话挂钩调用。"""
    auth = _RecreateAuth()
    cfg = PilotConfig(browser=BrowserSettings(base_url="https://app.example"))
    db = MagicMock()
    auth.recreate_test_account(cfg, db)
    assert auth.calls == [(cfg, db)]
