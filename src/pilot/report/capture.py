"""绑定当前 pytest item，供报告步骤 / extras 无 pytest 硬依赖写入。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_current_item: ContextVar[Any | None] = ContextVar("pilot_pytest_item", default=None)


def bind_test_item(item: Any) -> Token[Any | None]:
    """绑定当前用例 item，供 step / attach 写入。"""
    return _current_item.set(item)


def reset_test_item(token: Token[Any | None]) -> None:
    """恢复绑定前的 item。"""
    _current_item.reset(token)


def get_test_item() -> Any | None:
    """取当前绑定的 pytest item；未绑定时为 None。"""
    return _current_item.get()
