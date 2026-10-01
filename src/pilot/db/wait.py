"""轻量 poll-until：用于 DB 异步落库，禁止硬 sleep。"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PollResult:
    """``wait_until`` 成功时的结果快照。"""

    label: str
    elapsed_sec: float
    attempts: int
    last_snapshot: Any = None


def wait_until(
    label: str,
    predicate: Callable[[], bool],
    *,
    timeout_sec: float = 30.0,
    interval_sec: float = 0.5,
    on_poll: Callable[[], Any] | None = None,
) -> PollResult:
    """轮询 ``predicate`` 直至为真或超时。

    超时抛 ``AssertionError``，消息含 label / 耗时 / 尝试次数 / last_snapshot。
    """
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be positive")
    if interval_sec <= 0:
        raise ValueError("interval_sec must be positive")

    deadline = time.monotonic() + timeout_sec
    attempts = 0
    last_snapshot: Any = None
    start = time.monotonic()

    while True:
        attempts += 1
        if predicate():
            if on_poll is not None:
                last_snapshot = on_poll()
            elapsed = time.monotonic() - start
            return PollResult(
                label=label,
                elapsed_sec=elapsed,
                attempts=attempts,
                last_snapshot=last_snapshot,
            )

        if on_poll is not None:
            last_snapshot = on_poll()

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            elapsed = time.monotonic() - start
            raise AssertionError(
                f"wait_until timed out: {label!r} "
                f"(timeout={timeout_sec}s, elapsed={elapsed:.2f}s, "
                f"attempts={attempts}, last_snapshot={last_snapshot!r})"
            )

        time.sleep(min(interval_sec, remaining))
