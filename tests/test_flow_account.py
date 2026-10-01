"""BaseFlow 默认账号：无角色时用 config.default_account。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pilot.core.config import PilotConfig
from pilot.flow.base import BaseFlow


def _flow(accounts: dict, default_account: str = "test_user") -> BaseFlow:
    """构造仅含账号配置的 Flow，page 用 mock。"""
    config = PilotConfig(accounts=accounts, default_account=default_account)
    return BaseFlow(MagicMock(), config)


def test_account_without_role_uses_default() -> None:
    flow = _flow(
        {
            "ops": {"username": "ops1", "password": "a"},
            "test_user": {"username": "u1", "password": "b"},
        }
    )
    assert flow.account()["username"] == "u1"


def test_account_with_explicit_role() -> None:
    flow = _flow(
        {
            "ops": {"username": "ops1", "password": "a"},
            "test_user": {"username": "u1", "password": "b"},
        }
    )
    assert flow.account("ops")["username"] == "ops1"


def test_account_respects_custom_default_account() -> None:
    flow = _flow(
        {
            "ops": {"username": "ops1", "password": "a"},
            "test_user": {"username": "u1", "password": "b"},
        },
        default_account="ops",
    )
    assert flow.account()["username"] == "ops1"


def test_account_unknown_default_raises() -> None:
    flow = _flow({"ops": {"username": "ops1", "password": "a"}})
    with pytest.raises(KeyError, match="test_user"):
        flow.account()
