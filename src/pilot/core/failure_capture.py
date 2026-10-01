"""断言失败即时截图：绑定 Page/Artifacts，供 soft / assertx 共用。"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from pilot.core.artifacts import ArtifactCollector


@dataclass
class _CaptureState:
    """当前用例的失败截图上下文。"""

    page: Page
    artifacts: ArtifactCollector
    enabled: bool
    soft_index: int = 0
    captured: bool = False


_state: ContextVar[_CaptureState | None] = ContextVar(
    "pilot_failure_capture", default=None
)


def bind_failure_capture(
    page: Page,
    artifacts: ArtifactCollector,
    *,
    enabled: bool = True,
) -> None:
    """绑定本用例的 Page 与产物目录，供断言失败时截图。"""
    _state.set(_CaptureState(page=page, artifacts=artifacts, enabled=enabled))


def clear_failure_capture() -> None:
    """解除绑定（fixture teardown 时调用）。"""
    _state.set(None)


def was_assertion_screenshot_taken() -> bool:
    """本用例是否已有断言失败截图（供 teardown 去重）。"""
    state = _state.get()
    return bool(state and state.captured)


def attach_screenshot_to_failure(
    error: AssertionError,
    *,
    soft: bool = False,
) -> AssertionError:
    """若已绑定且开启，截图并把路径追加到异常文案；失败则原样返回。

    soft=True 时按 soft_1 / soft_2 … 命名；否则为 assert_failure。
    """
    state = _state.get()
    if state is None or not state.enabled:
        return error

    if soft:
        state.soft_index += 1
        name = f"soft_{state.soft_index}"
    else:
        name = "assert_failure"

    path = state.artifacts.screenshot(state.page, name)
    if path is None:
        return error

    state.captured = True
    return _append_screenshot_path(error, state.artifacts.link_for(path))


def _append_screenshot_path(error: AssertionError, link: str) -> AssertionError:
    """在原消息末尾追加可点击的 screenshot 相对路径。"""
    base = str(error).rstrip()
    line = f"screenshot: {link}"
    if line in base:
        return error
    return AssertionError(f"{base}\n{line}")
