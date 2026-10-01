"""单用例多线程并发原语（产品无关）。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class ConcurrentErrors(Exception):
    """run_concurrent 多路失败时的汇总异常。"""

    def __init__(self, exceptions: list[BaseException]) -> None:
        self.exceptions = list(exceptions)
        super().__init__(f"{len(self.exceptions)} concurrent task(s) failed")


def _closure_values(fn: Callable[..., Any]) -> list[Any]:
    """读取闭包 cell 内容（最佳努力）。"""
    values: list[Any] = []
    closure = getattr(fn, "__closure__", None) or ()
    for cell in closure:
        try:
            values.append(cell.cell_contents)
        except ValueError:
            continue
    return values


def _cells_with_playwright_id(fn: Callable[..., Any]) -> list[int]:
    """从闭包 cell 收集带 ``_playwright_id`` 的对象 id（最佳努力）。"""
    found: list[int] = []
    for val in _closure_values(fn):
        pid = getattr(val, "_playwright_id", None)
        if isinstance(pid, int):
            found.append(pid)
    return found


def _pw_thread_from_callable(fn: Callable[..., Any]) -> Any | None:
    """若闭包捕获带 ``_pw_thread`` 的 Flow，返回其线程（同闭包多路不同线程则报错）。"""
    threads: list[Any] = []
    for val in _closure_values(fn):
        thr = getattr(val, "_pw_thread", None)
        if thr is not None:
            threads.append(thr)
    if not threads:
        return None
    uniq = {id(t) for t in threads}
    if len(uniq) > 1:
        raise RuntimeError(
            "run_concurrent: one callable closes over Flows with different "
            "Playwright threads; split into separate callables."
        )
    return threads[0]


def collect_playwright_ids_from_callables(
    fns: tuple[Callable[..., Any], ...],
) -> list[int]:
    """汇总各 callable 闭包中的 Playwright id。"""
    ids: list[int] = []
    for fn in fns:
        ids.extend(_cells_with_playwright_id(fn))
    return ids


def assert_distinct_playwrights(fns: tuple[Callable[..., Any], ...]) -> None:
    """若闭包里出现重复 ``_playwright_id``，拒绝进入并发。"""
    ids = collect_playwright_ids_from_callables(fns)
    if len(ids) != len(set(ids)):
        raise RuntimeError(
            "run_concurrent: concurrent callables share the same Playwright; "
            "use flow.spawn_browser(isolated=True) per participant "
            "(main flow must not drive pages inside worker threads)."
        )


def run_concurrent(
    *fns: Callable[[], Any],
    timeout: float | None = None,
) -> tuple[Any, ...]:
    """在独立线程中齐射执行 ``fns``，按入参顺序返回结果。

    若闭包捕获了 ``spawn_browser(isolated=True)`` 产生的 Flow，则把任务投递到
    各 Flow 的 Playwright 专属线程（sync API 要求）。

    全部结束后再抛错：单失败原样抛出；多失败抛 ``ConcurrentErrors``。
    ``timeout`` 为总等待秒数；超时抛 ``TimeoutError``（不保证停掉未结束线程内的 Playwright）。
    """
    if len(fns) < 2:
        raise ValueError("run_concurrent requires at least 2 callables")

    assert_distinct_playwrights(fns)

    pw_threads = [_pw_thread_from_callable(fn) for fn in fns]
    if any(t is not None for t in pw_threads) and not all(
        t is not None for t in pw_threads
    ):
        raise RuntimeError(
            "run_concurrent: mix of isolated and non-isolated Flows; "
            "all participants must use spawn_browser(isolated=True)."
        )

    barrier = threading.Barrier(len(fns))
    results: list[Any] = [None] * len(fns)
    errors: list[BaseException | None] = [None] * len(fns)

    def run_one(index: int, fn: Callable[[], Any]) -> None:
        try:
            # 齐射：全部到齐后再跑业务
            barrier.wait(timeout=timeout if timeout is not None else 30)
            results[index] = fn()
        except BaseException as exc:  # noqa: BLE001 — 需汇总后抛
            errors[index] = exc

    if all(t is not None for t in pw_threads):
        # isolated：任务在各自 PlaywrightThread 上跑（线程已存在）
        joiners: list[threading.Thread] = []

        def submit(index: int, fn: Callable[[], Any], thr: Any) -> None:
            def bridge() -> None:
                thr.call(lambda: run_one(index, fn))

            t = threading.Thread(target=bridge, daemon=True)
            joiners.append(t)
            t.start()

        for i, (fn, thr) in enumerate(zip(fns, pw_threads, strict=True)):
            submit(i, fn, thr)
        for t in joiners:
            t.join(timeout=timeout)
            if t.is_alive():
                raise TimeoutError(
                    f"run_concurrent timed out after {timeout}s "
                    "(in-flight Playwright work may continue until the process exits)"
                )
    else:
        threads = [
            threading.Thread(target=run_one, args=(i, fn), daemon=True)
            for i, fn in enumerate(fns)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=timeout)
            if t.is_alive():
                raise TimeoutError(
                    f"run_concurrent timed out after {timeout}s "
                    "(in-flight Playwright work may continue until the process exits)"
                )

    failed = [e for e in errors if e is not None]
    if len(failed) == 1:
        raise failed[0]
    if len(failed) > 1:
        raise ConcurrentErrors(failed)
    return tuple(results)
