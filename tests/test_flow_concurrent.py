"""flow.run_concurrent：产品无关并发原语。"""

from __future__ import annotations

import threading
import time

import pytest

from pilot.flow.concurrent import ConcurrentErrors, assert_distinct_playwrights, run_concurrent


def test_run_concurrent_requires_at_least_two() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        run_concurrent(lambda: 1)


def test_run_concurrent_returns_results_in_order() -> None:
    results = run_concurrent(lambda: "a", lambda: "b", lambda: "c")
    assert results == ("a", "b", "c")


def test_run_concurrent_runs_in_parallel() -> None:
    """两路各 sleep 0.3s；墙钟应明显小于串行合计。"""
    barrier = threading.Barrier(2)

    def one() -> str:
        barrier.wait(timeout=2)
        time.sleep(0.3)
        return "one"

    def two() -> str:
        barrier.wait(timeout=2)
        time.sleep(0.3)
        return "two"

    t0 = time.perf_counter()
    assert run_concurrent(one, two) == ("one", "two")
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.55


def test_run_concurrent_single_failure_reraises() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        run_concurrent(lambda: 1, lambda: (_ for _ in ()).throw(RuntimeError("boom")))


def test_run_concurrent_multiple_failures_group() -> None:
    def fail_a() -> None:
        raise ValueError("a")

    def fail_b() -> None:
        raise TypeError("b")

    with pytest.raises(ConcurrentErrors) as ei:
        run_concurrent(fail_a, fail_b)
    assert len(ei.value.exceptions) == 2
    types = {type(e) for e in ei.value.exceptions}
    assert types == {ValueError, TypeError}


def test_run_concurrent_timeout() -> None:
    def slow() -> None:
        time.sleep(2)

    with pytest.raises(TimeoutError):
        run_concurrent(lambda: None, slow, timeout=0.2)


def test_assert_distinct_playwrights_rejects_duplicate() -> None:
    class Holder:
        def __init__(self, pid: int) -> None:
            self._playwright_id = pid

    a = Holder(1)
    b = Holder(1)
    with pytest.raises(RuntimeError, match="Playwright"):
        assert_distinct_playwrights((lambda: a, lambda: b))
