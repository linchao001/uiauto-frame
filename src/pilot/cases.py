"""UI 用例数据驱动：YAML → Case，经 @cases 展开为 pytest parametrize。

面向同流程、不同输入/期望的 UI 场景；每行数据独立 node（各自截图/trace）。
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import pytest
import yaml

F = TypeVar("F", bound=Callable[..., Any])


class AttrMap:
    """只读属性视图：嵌套 dict 继续包一层，便于 case.input.username。"""

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_data", dict(data))

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
        if isinstance(value, Mapping):
            return AttrMap(value)
        return value

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def as_dict(self) -> dict[str, Any]:
        """返回底层浅拷贝，供需要 mapping 的调用方使用。"""
        return dict(self._data)

    def __repr__(self) -> str:
        return f"AttrMap({self._data!r})"


@dataclass(frozen=True)
class Case:
    """单行 UI 用例数据：id + input + expect。"""

    id: str
    input: AttrMap
    expect: AttrMap


def load_cases(path: Path | str) -> list[Case]:
    """从 YAML 列表加载 Case；校验必填字段与 id 唯一性。"""
    file_path = Path(path)
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"cases file must be a YAML list: {file_path}")

    cases_out: list[Case] = []
    seen: set[str] = set()
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise ValueError(f"case[{index}] must be a mapping in {file_path}")
        case_id = row.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"case[{index}] missing non-empty 'id' in {file_path}")
        if case_id in seen:
            raise ValueError(f"duplicate id {case_id!r} in {file_path}")
        seen.add(case_id)

        if "input" not in row:
            raise ValueError(f"case {case_id!r} missing 'input' in {file_path}")
        if "expect" not in row:
            raise ValueError(f"case {case_id!r} missing 'expect' in {file_path}")
        input_data = row["input"]
        expect_data = row["expect"]
        if not isinstance(input_data, Mapping):
            raise ValueError(f"case {case_id!r} 'input' must be a mapping in {file_path}")
        if not isinstance(expect_data, Mapping):
            raise ValueError(f"case {case_id!r} 'expect' must be a mapping in {file_path}")

        cases_out.append(
            Case(
                id=case_id,
                input=AttrMap(input_data),
                expect=AttrMap(expect_data),
            )
        )
    return cases_out


def _resolve_cases_path(func: Callable[..., Any], relative: str) -> Path:
    """相对被装饰函数所在模块文件解析数据路径。"""
    module = inspect.getmodule(func)
    mod_name = getattr(func, "__module__", None)
    if module is None and mod_name:
        module = sys.modules.get(mod_name)
    file_name = getattr(module, "__file__", None) if module is not None else None
    if not file_name:
        raise pytest.UsageError(
            f"@cases({relative!r}): cannot resolve path; "
            f"function {func.__qualname__!r} has no module __file__"
        )
    path = Path(file_name).resolve().parent / relative
    if not path.is_file():
        raise pytest.UsageError(
            f"@cases({relative!r}): file not found: {path}"
        )
    return path


def cases(relative_path: str) -> Callable[[F], F]:
    """按相对用例文件的 YAML 展开 pytest.mark.parametrize(\"case\", ..., ids=...).

    适用：同 UI 流程、不同输入/期望。勿把不同流程硬塞进同一文件。
    """

    def decorator(func: F) -> F:
        path = _resolve_cases_path(func, relative_path)
        loaded = load_cases(path)
        return pytest.mark.parametrize(
            "case",
            loaded,
            ids=[c.id for c in loaded],
        )(func)

    return decorator
