"""为独立 Playwright 实例提供专属线程（sync API 同线程不能二次 start）。"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class PlaywrightThread:
    """在后台线程持有 event loop，供该线程独占一套 sync Playwright。"""

    def __init__(self, *, name: str = "pilot-pw") -> None:
        self._jobs: queue.Queue[
            tuple[Callable[[], object], dict[str, object]] | None
        ] = queue.Queue()
        self._thread = threading.Thread(target=self._main, name=name, daemon=True)
        self._ready = threading.Event()
        self._thread.start()
        if not self._ready.wait(timeout=60):
            raise RuntimeError("PlaywrightThread failed to start")

    def _main(self) -> None:
        self._ready.set()
        while True:
            item = self._jobs.get()
            if item is None:
                break
            fn, fut = item
            done = fut["done"]
            assert isinstance(done, threading.Event)
            try:
                fut["result"] = fn()
            except BaseException as exc:  # noqa: BLE001 — 带回调用方
                fut["error"] = exc
            finally:
                done.set()

    def call(self, fn: Callable[[], T]) -> T:
        """在本线程执行 ``fn``；若已在本线程则直接调用。"""
        if threading.current_thread() is self._thread:
            return fn()
        fut: dict[str, object] = {
            "done": threading.Event(),
            "result": None,
            "error": None,
        }
        self._jobs.put((fn, fut))
        done = fut["done"]
        assert isinstance(done, threading.Event)
        done.wait()
        err = fut["error"]
        if err is not None:
            assert isinstance(err, BaseException)
            raise err
        return fut["result"]  # type: ignore[return-value]

    def stop(self) -> None:
        """结束工作线程（应在 Playwright 已 stop 之后调用）。"""
        self._jobs.put(None)
        self._thread.join(timeout=30)
