"""scaffold 生成的 Flow.open_as 只把角色 key 与页面 URL 交给框架。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pilot.core.config import BrowserSettings, PilotConfig
from pilot.flow.base import BaseFlow
from pilot.scaffold import create_case_repo

_PRODUCT_TOP = ("actions", "pages", "checks", "flow", "cases", "account")


def _activate_repo(repo: Path) -> None:
    """把 ``repo`` 置为 sys.path 首位，并清掉旧的产品仓模块缓存。"""
    for key in list(sys.modules):
        if key in _PRODUCT_TOP or key.startswith(tuple(f"{p}." for p in _PRODUCT_TOP)):
            del sys.modules[key]
    root = str(repo)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)


@pytest.fixture
def scaffold_repo(tmp_path: Path) -> Path:
    """生成最小产品仓并激活 import。"""
    dest = tmp_path / "product"
    create_case_repo(dest)
    _activate_repo(dest)
    return dest


def _flow():
    from flow import Flow

    config = PilotConfig(
        browser=BrowserSettings(base_url="https://app.example"),
        accounts={"test_user": {"username": "u1", "password": "secret"}},
    )
    return Flow(MagicMock(), config)


def test_open_as_passes_account_key_and_path(
    scaffold_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pages.home_page import HomePage

    calls: list[tuple[str, str]] = []

    def _open(self, role, page_url):
        calls.append((role, page_url))

    waited: list[bool] = []
    monkeypatch.setattr(BaseFlow, "open_as", _open)
    monkeypatch.setattr(HomePage, "wait_ready", lambda self: waited.append(True))

    _flow().open_as("role_a", "home")

    assert calls == [("test_user", "/home")]
    assert waited == [True]
