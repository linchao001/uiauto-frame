"""scaffold 生成的角色 / 页面映射（定义在 actions/auth.py）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

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


def test_resolve_role_account_key(scaffold_repo: Path) -> None:
    from actions.auth import resolve_role_account_key

    assert resolve_role_account_key("role_a") == "test_user"


def test_resolve_role_unknown(scaffold_repo: Path) -> None:
    from actions.auth import resolve_role_account_key

    with pytest.raises(KeyError, match="未知角色"):
        resolve_role_account_key("unknown_role")


def test_resolve_page_path(scaffold_repo: Path) -> None:
    from actions.auth import resolve_page_path

    assert resolve_page_path("home") == "/home"


def test_resolve_page_unknown(scaffold_repo: Path) -> None:
    from actions.auth import resolve_page_path

    with pytest.raises(KeyError, match="未知页面"):
        resolve_page_path("missing_page")
