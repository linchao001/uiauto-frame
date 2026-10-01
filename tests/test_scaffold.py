"""pilot init：按框架约定生成产品用例仓库。"""

from __future__ import annotations

from pathlib import Path

import pytest

from pilot.cli import main
from pilot.scaffold import ScaffoldError, create_case_repo


EXPECTED_FILES = {
    ".gitignore",
    "flow.py",
    "conftest.py",
    "account/__init__.py",
    "account/auth.py",
    "pages/__init__.py",
    "pages/home_page.py",
    "pages/login_page.py",
    "actions/__init__.py",
    "actions/auth.py",
    "checks/__init__.py",
    "checks/home.py",
    "cases/test_login.py",
    "config/product.yaml",
    "config/env/lab.yaml.example",
}


def test_create_case_repo_generates_required_layout(tmp_path: Path) -> None:
    dest = tmp_path / "acme"
    written = create_case_repo(dest)
    rels = {path.as_posix() for path in written}
    assert rels == EXPECTED_FILES
    product_yaml = (dest / "config" / "product.yaml").read_text(encoding="utf-8")
    assert "product: acme" in product_yaml
    assert "env: lab" in product_yaml
    assert "default_account: test_user" in product_yaml
    assert "AuthProvider" in product_yaml or "鉴权协议由产品实现" in product_yaml
    assert "AuthProvider" in (dest / "account" / "auth.py").read_text(encoding="utf-8")
    example = (dest / "config" / "env" / "lab.yaml.example").read_text(encoding="utf-8")
    assert "https://device.example" in example
    assert "changeme" in example
    assert "test_user:" in example
    assert "框架不解析" in example or "AuthProvider" in example or "account/auth.py" in example
    assert not (dest / "config" / "env" / "lab.yaml").exists()
    gitignore = (dest / ".gitignore").read_text(encoding="utf-8")
    assert "config/env/*.yaml" in gitignore
    assert "*.yaml.example" in gitignore
    case_names = sorted(p.name for p in (dest / "cases").glob("*.py"))
    assert case_names == ["test_login.py"]
    assert "TODO" in (dest / "pages" / "home_page.py").read_text(encoding="utf-8")
    assert "register_auth_provider" in (dest / "conftest.py").read_text(encoding="utf-8")


def test_create_case_repo_product_flag_overrides_dirname(tmp_path: Path) -> None:
    dest = tmp_path / "folder_name"
    create_case_repo(dest, product="demo")
    text = (dest / "config" / "product.yaml").read_text(encoding="utf-8")
    assert "product: demo" in text
    assert "product: folder_name" not in text


def test_create_case_repo_refuses_non_empty_unless_force(tmp_path: Path) -> None:
    dest = tmp_path / "product"
    create_case_repo(dest)
    (dest / "notes.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ScaffoldError, match="不是空的"):
        create_case_repo(dest)
    assert (dest / "notes.txt").read_text(encoding="utf-8") == "keep"

    create_case_repo(dest, product="rev2", force=True)
    assert "product: rev2" in (dest / "config" / "product.yaml").read_text(encoding="utf-8")
    assert (dest / "notes.txt").is_file()
