"""flow.spawn_browser：单条用例再启独立浏览器进程。"""

from __future__ import annotations

from pathlib import Path

import pytest

from pilot.core.browser import (
    BrowserSession,
    SharedBrowser,
    launch_browser,
    launch_extra_browser,
    launch_isolated_session,
    open_page,
)
from pilot.core.config import BrowserSettings, PilotConfig
from pilot.flow.base import BaseFlow


class _DemoFlow(BaseFlow):
    """最小产品 Flow，用于验证 spawn_browser 返回同型实例。"""

    marker: str = "root"


def _settings() -> BrowserSettings:
    return BrowserSettings(headless=True, trace="off", video="off")


def test_spawn_browser_without_binding_raises() -> None:
    """未挂到 pytest flow fixture 时，spawn_browser 应明确失败。"""
    flow = _DemoFlow(page=object(), config=PilotConfig())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="spawn_browser"):
        flow.spawn_browser()


def test_spawn_browser_uses_new_browser_same_playwright(tmp_path: Path) -> None:
    """spawn_browser 新开 Browser；子 Flow 再 spawn 落在该 Browser 上。"""
    shared = launch_browser(_settings())
    sessions: list[BrowserSession] = []
    try:
        primary = open_page(shared, _settings(), artifacts_dir=tmp_path / "a")
        sessions.append(primary)

        def open_ctx() -> BrowserSession:
            s = open_page(shared, _settings(), artifacts_dir=tmp_path / f"ctx-{len(sessions)}")
            sessions.append(s)
            return s

        def make_open_browser(playwright):
            def open_browser(*, isolated: bool = False):
                if isolated:
                    iso = launch_browser(_settings())
                    first = open_page(
                        iso, _settings(), artifacts_dir=tmp_path / f"iso-{len(sessions)}"
                    )
                    first.owns_browser = True
                    first.owns_playwright = True
                    sessions.append(first)

                    def open_on_iso() -> BrowserSession:
                        s = open_page(
                            iso,
                            _settings(),
                            artifacts_dir=tmp_path / f"iso-ctx-{len(sessions)}",
                        )
                        sessions.append(s)
                        return s

                    return first, open_on_iso, make_open_browser(iso.playwright)

                extra = launch_extra_browser(playwright, _settings())
                wrapper = SharedBrowser(playwright=playwright, browser=extra)
                first = open_page(
                    wrapper, _settings(), artifacts_dir=tmp_path / f"br-{len(sessions)}"
                )
                first.owns_browser = True
                first.owns_playwright = False
                sessions.append(first)

                def open_on_extra() -> BrowserSession:
                    s = open_page(
                        wrapper,
                        _settings(),
                        artifacts_dir=tmp_path / f"br-ctx-{len(sessions)}",
                    )
                    sessions.append(s)
                    return s

                return first, open_on_extra, make_open_browser(playwright)

            return open_browser

        open_browser = make_open_browser(shared.playwright)

        def factory(page, config):
            return _DemoFlow(page, config)

        root = factory(primary.page, PilotConfig())
        root.bind_spawner(
            factory,
            PilotConfig(),
            open_ctx,
            open_browser,
            playwright_id=id(shared.playwright),
        )

        child = root.spawn_browser()
        assert isinstance(child, _DemoFlow)
        assert child.page.context.browser is not root.page.context.browser
        # 同一 Playwright：再 spawn Context 应落在 child 的 browser 上
        grandchild = child.spawn()
        assert grandchild.page.context.browser is child.page.context.browser
        assert grandchild.page.context is not child.page.context
    finally:
        for s in reversed(sessions):
            s.close()
        shared.close()


def test_spawn_browser_isolated_uses_own_playwright(tmp_path: Path) -> None:
    """isolated=True：专属线程上新 Playwright；owns_playwright；与主 PW 不同。"""
    shared = launch_browser(_settings())
    sessions: list[BrowserSession] = []
    threads_to_stop: list = []
    try:
        primary = open_page(shared, _settings(), artifacts_dir=tmp_path / "a")
        sessions.append(primary)

        def open_ctx() -> BrowserSession:
            s = open_page(shared, _settings(), artifacts_dir=tmp_path / f"ctx-{len(sessions)}")
            sessions.append(s)
            return s

        def make_open_browser(playwright, pw_thread=None):
            def open_browser(*, isolated: bool = False):
                if isolated:
                    first, thr = launch_isolated_session(
                        _settings(),
                        artifacts_dir=tmp_path / f"iso-{len(sessions)}",
                    )
                    sessions.append(first)
                    threads_to_stop.append(thr)

                    def open_on_iso() -> BrowserSession:
                        s = thr.call(
                            lambda: open_page(
                                SharedBrowser(
                                    playwright=first.playwright, browser=first.browser
                                ),
                                _settings(),
                                artifacts_dir=tmp_path / f"iso-ctx-{len(sessions)}",
                            )
                        )
                        s.pw_thread = thr
                        sessions.append(s)
                        return s

                    return first, open_on_iso, make_open_browser(first.playwright, thr)

                def _launch_extra():
                    extra = launch_extra_browser(playwright, _settings())
                    wrapper = SharedBrowser(playwright=playwright, browser=extra)
                    first = open_page(
                        wrapper, _settings(), artifacts_dir=tmp_path / f"br-{len(sessions)}"
                    )
                    first.owns_browser = True
                    first.owns_playwright = False
                    first.pw_thread = pw_thread
                    return first, wrapper

                if pw_thread is not None:
                    first, wrapper = pw_thread.call(_launch_extra)
                else:
                    first, wrapper = _launch_extra()
                sessions.append(first)

                def open_on_extra() -> BrowserSession:
                    def _open():
                        s = open_page(
                            wrapper,
                            _settings(),
                            artifacts_dir=tmp_path / f"br-ctx-{len(sessions)}",
                        )
                        s.pw_thread = pw_thread
                        return s

                    s = pw_thread.call(_open) if pw_thread is not None else _open()
                    sessions.append(s)
                    return s

                return first, open_on_extra, make_open_browser(playwright, pw_thread)

            return open_browser

        open_browser = make_open_browser(shared.playwright)

        def factory(page, config):
            return _DemoFlow(page, config)

        root = factory(primary.page, PilotConfig())
        root.bind_spawner(
            factory,
            PilotConfig(),
            open_ctx,
            open_browser,
            playwright_id=id(shared.playwright),
        )
        assert root._playwright_id == id(shared.playwright)

        child = root.spawn_browser(isolated=True)
        assert child._playwright_id is not None
        assert child._playwright_id != root._playwright_id
        assert child._pw_thread is not None
        iso_session = sessions[-1]
        assert iso_session.owns_playwright is True
        assert iso_session.playwright is not shared.playwright

        # 子路再 spawn 仍在同一 isolated Browser / 线程
        grand = child.spawn()
        assert grand._playwright_id == child._playwright_id
        assert grand._pw_thread is child._pw_thread
    finally:
        for s in reversed(sessions):
            thr = s.pw_thread
            if thr is not None:
                thr.call(s.close)
            else:
                s.close()
        for thr in threads_to_stop:
            thr.stop()
        shared.close()


def test_flow_run_concurrent_delegates() -> None:
    """BaseFlow.run_concurrent 可调用；两路不同 Playwright id 闭包不冲突。"""
    left = _DemoFlow(page=object(), config=PilotConfig())  # type: ignore[arg-type]
    right = _DemoFlow(page=object(), config=PilotConfig())  # type: ignore[arg-type]
    left._playwright_id = 101
    right._playwright_id = 202
    out = left.run_concurrent(lambda: left._playwright_id, lambda: right._playwright_id)
    assert out == (101, 202)
