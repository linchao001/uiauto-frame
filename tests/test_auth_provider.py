"""AuthProvider：框架只提供基类；未实现时须明确失败。"""

from __future__ import annotations

from typing import Any

import pytest

from pilot.account.auth import AuthProvider, UnsetAuthProvider
from pilot.core.config import PilotConfig


class _MinimalAuth(AuthProvider):
    """测试用最小实现（仅 login + token_store）。"""

    def login(self, *, base_url: str, username: str, password: str) -> dict[str, Any]:
        return {"u": username, "p": password, "base": base_url}

    def token_store_items(self, login_data: dict[str, Any]) -> dict[str, str]:
        return {"tok": str(login_data)}


def test_auth_provider_subclass_works() -> None:
    auth = _MinimalAuth()
    assert auth.login(base_url="http://x", username="a", password="b")["u"] == "a"
    assert auth.token_store_items({"k": 1}) == {"tok": "{'k': 1}"}


def test_recreate_and_report_default_noop() -> None:
    auth = _MinimalAuth()
    auth.recreate_test_account(PilotConfig(), db=None)
    assert auth.report_version_fields(PilotConfig()) == {}


def test_unset_login_raises_with_guidance() -> None:
    auth = UnsetAuthProvider()
    with pytest.raises(RuntimeError, match="AuthProvider"):
        auth.login(base_url="http://x", username="a", password="b")
    with pytest.raises(RuntimeError, match="AuthProvider"):
        auth.token_store_items({})


def test_incomplete_subclass_cannot_instantiate() -> None:
    class _Bad(AuthProvider):
        pass

    with pytest.raises(TypeError):
        _Bad()  # type: ignore[abstract]
