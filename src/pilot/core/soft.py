"""软断言：在作用域内收集 AssertionError，退出或 assert_all 时一次性抛出。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from pilot.core.failure_capture import attach_screenshot_to_failure

# 当前测试上下文中的软断言收集器；None 表示硬断言模式
_current: ContextVar[_SoftCollector | None] = ContextVar("pilot_soft_assertions", default=None)


class _SoftCollector:
    """收集软断言失败信息。"""

    def __init__(self) -> None:
        self.failures: list[AssertionError] = []

    def add(self, error: AssertionError) -> None:
        self.failures.append(error)

    def assert_all(self) -> None:
        """若有失败则按块汇总抛出，并清空列表。"""
        if not self.failures:
            return
        count = len(self.failures)
        # 每条失败单独一块，便于阅读已表格化的 diff（单条 error 日志已在抛出时打过）
        parts = [f"Soft assertion failures ({count}):"]
        for i, err in enumerate(self.failures, start=1):
            parts.append(f"[{i}]")
            parts.append(str(err))
        self.failures.clear()
        raise AssertionError("\n".join(parts))


def is_soft_mode() -> bool:
    """当前是否处于 soft_assertions 作用域。"""
    return _current.get() is not None


def run_assertion(fn: Callable[[], Any]) -> None:
    """执行一次断言：硬模式直接跑；软模式捕获 AssertionError 并记录。

    失败时若已绑定 failure_capture，会即时截图并把路径写入异常文案。
    """
    collector = _current.get()
    if collector is None:
        try:
            fn()
        except AssertionError as exc:
            raise attach_screenshot_to_failure(exc, soft=False) from None
        return
    try:
        fn()
    except AssertionError as exc:
        collector.add(attach_screenshot_to_failure(exc, soft=True))


def assert_all() -> None:
    """显式汇总当前软断言失败；无活动收集器时为空操作。"""
    collector = _current.get()
    if collector is None:
        return
    collector.assert_all()


@contextmanager
def soft_assertions() -> Iterator[None]:
    """软断言作用域：内部 expect_* / run_assertion 失败会继续，退出时汇总抛出。

    禁止嵌套。可在作用域内提前调用 ``assert_all()`` 冲刷失败。
    """
    if _current.get() is not None:
        raise RuntimeError("Cannot nest soft_assertions()")
    collector = _SoftCollector()
    token = _current.set(collector)
    try:
        yield
        # 正常离开 with 体时汇总；若体中已 assert_all 抛错则不会走到这里
        collector.assert_all()
    finally:
        _current.reset(token)
