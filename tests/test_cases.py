"""@pilot.cases：UI 用例数据驱动加载与 parametrize。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from pilot.cases import Case, cases, load_cases


def test_load_cases_builds_attr_case(tmp_path: Path) -> None:
    """合法 YAML 行应得到可属性访问的 Case（input/expect）。"""
    data = tmp_path / "login.yaml"
    data.write_text(
        """
- id: empty_password
  input:
    username: buyer
    password: ""
  expect:
    error_visible: true
    error_text: 请输入密码
""",
        encoding="utf-8",
    )
    loaded = load_cases(data)
    assert len(loaded) == 1
    case = loaded[0]
    assert isinstance(case, Case)
    assert case.id == "empty_password"
    assert case.input.username == "buyer"
    assert case.input.password == ""
    assert case.expect.error_visible is True
    assert case.expect.error_text == "请输入密码"


def test_load_cases_rejects_missing_required_fields(tmp_path: Path) -> None:
    """缺 id / input / expect 时应明确失败。"""
    data = tmp_path / "bad.yaml"
    data.write_text(
        """
- id: only_id
  input:
    x: 1
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expect"):
        load_cases(data)


def test_load_cases_rejects_duplicate_id(tmp_path: Path) -> None:
    """同一文件内 id 必须唯一。"""
    data = tmp_path / "dup.yaml"
    data.write_text(
        """
- id: same
  input: {}
  expect: {}
- id: same
  input: {}
  expect: {}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate id"):
        load_cases(data)


def test_cases_decorator_resolves_relative_to_test_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@cases 路径相对用例 .py；pytest ids 使用 case.id。"""
    case_dir = tmp_path / "cases" / "login"
    (case_dir / "testdata").mkdir(parents=True)
    (case_dir / "testdata" / "login.yaml").write_text(
        """
- id: ok_login
  input:
    username: buyer
  expect:
    landed: true
- id: bad_login
  input:
    username: ""
  expect:
    landed: false
""",
        encoding="utf-8",
    )

    fake_mod = ModuleType("fake_login_cases")
    fake_mod.__file__ = str(case_dir / "test_login.py")
    monkeypatch.setitem(sys.modules, "fake_login_cases", fake_mod)

    def test_login(case: Case) -> None:
        assert case.id in {"ok_login", "bad_login"}

    test_login.__module__ = "fake_login_cases"
    decorated = cases("testdata/login.yaml")(test_login)

    marks = getattr(decorated, "pytestmark", [])
    if not isinstance(marks, list):
        marks = [marks]
    param_marks = [m for m in marks if m.name == "parametrize"]
    assert len(param_marks) == 1
    assert param_marks[0].args[0] == "case"
    assert param_marks[0].kwargs.get("ids") == ["ok_login", "bad_login"]
    assert [c.id for c in param_marks[0].args[1]] == ["ok_login", "bad_login"]


def test_cases_decorator_missing_file_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """相对路径找不到文件时给出明确错误。"""
    case_dir = tmp_path / "cases"
    case_dir.mkdir()
    fake_mod = ModuleType("fake_missing_cases")
    fake_mod.__file__ = str(case_dir / "test_x.py")
    monkeypatch.setitem(sys.modules, "fake_missing_cases", fake_mod)

    def test_x(case: Case) -> None:
        del case

    test_x.__module__ = "fake_missing_cases"
    with pytest.raises(pytest.UsageError, match="testdata/missing.yaml"):
        cases("testdata/missing.yaml")(test_x)
