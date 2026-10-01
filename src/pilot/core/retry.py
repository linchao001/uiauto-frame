"""Retry helpers for flaky UI operations."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

T = TypeVar("T")

# 仅匹配「瞬时可恢复」的 actionability / 生命周期类错误；strict 等定位错误不在此列
# 可见性/启用态通常已由单次 timeout 内的 actionability 等待覆盖，失败多为 TimeoutError
_TRANSIENT_MARKERS = (
    "not attached",
    "detached from the dom",
    "intercepts pointer events",
    "not stable",
)


def is_retryable(exc: BaseException) -> bool:
    """判断是否值得对操作做短重试。

    Timeout 与典型 actionability 抖动可重试；strict 多匹配等定位错误应立即失败，
    避免拖长失败用例并掩盖断言前的真实原因。
    """
    if isinstance(exc, PlaywrightTimeoutError):
        return True
    if not isinstance(exc, PlaywrightError):
        return False
    msg = str(exc).lower()
    # strict / 解析类错误：重试不会变好
    if "strict mode violation" in msg:
        return False
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


def action_timeout_ms(timeout_ms: int, attempt: int) -> int:
    """按尝试次数分配操作超时：首次全额，重试半额以控制最坏墙钟时间。"""
    if attempt <= 0:
        return timeout_ms
    return max(timeout_ms // 2, 1)


def retry_action(
    fn: Callable[[], T],
    *,
    retries: int = 2,
    delay_ms: int = 400,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """Run ``fn`` with short retries for transient Playwright failures."""
    attempt = 0
    while True:
        try:
            return fn()
        except PlaywrightError as exc:
            # TimeoutError 是 PlaywrightError 子类；非瞬态（如 strict）直接抛出
            if not is_retryable(exc) or attempt >= retries:
                raise
            attempt += 1
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(delay_ms / 1000)
