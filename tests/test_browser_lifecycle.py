"""会话级浏览器进程：用例之间复用 Browser，各自新建 Context。"""

from __future__ import annotations

from pathlib import Path

from pilot.core.browser import (
    SharedBrowser,
    launch_browser,
    launch_extra_browser,
    launch_session,
    open_page,
)
from pilot.core.config import BrowserSettings
from pilot.pytest_plugin import pilot_browser, pilot_page


def _settings() -> BrowserSettings:
    # 关掉 trace/video，避免测试自己留下产物
    return BrowserSettings(headless=True, trace="off", video="off")


def test_pytest_fixtures_share_browser_per_session() -> None:
    """插件约定：浏览器是 session，页面是 function。"""
    assert pilot_browser._fixture_function_marker.scope == "session"  # type: ignore[attr-defined]
    assert pilot_page._fixture_function_marker.scope == "function"  # type: ignore[attr-defined]


def test_open_page_reuses_browser_and_isolates_context(tmp_path: Path) -> None:
    """关掉一条用例的 context 后，共享浏览器仍然连着，下一条是新 context。"""
    shared = launch_browser(_settings())
    try:
        first = open_page(shared, _settings(), artifacts_dir=tmp_path / "a")
        second = open_page(shared, _settings(), artifacts_dir=tmp_path / "b")
        assert first.browser is second.browser
        assert first.context is not second.context
        assert not first.owns_browser

        first.close()
        assert shared.browser.is_connected()
        second.page.goto("about:blank")
        second.close()
        assert shared.browser.is_connected()
    finally:
        shared.close()


def test_open_page_without_artifacts_dir_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    """不传产物目录时，即使配置了失败留证也不建 artifacts/。"""
    monkeypatch.chdir(tmp_path)
    settings = BrowserSettings(
        headless=True,
        trace="retain-on-failure",
        video="retain-on-failure",
    )
    shared = launch_browser(settings)
    try:
        session = open_page(shared, settings)
        assert session.trace_path is None
        session.close()
    finally:
        shared.close()
    assert not (tmp_path / "artifacts").exists()


def test_launch_session_close_stops_its_own_browser(tmp_path: Path) -> None:
    """兼容入口仍自带进程：close 必须把浏览器停掉，避免泄漏。"""
    session = launch_session(_settings(), artifacts_dir=tmp_path)
    browser = session.browser
    assert session.owns_browser
    assert session.owns_playwright
    session.close()
    assert not browser.is_connected()


def test_extra_browser_close_does_not_stop_playwright(tmp_path: Path) -> None:
    """spawn_browser 场景：关额外 Browser 不得 stop 共享 Playwright。"""
    shared = launch_browser(_settings())
    try:
        extra = launch_extra_browser(shared.playwright, _settings())
        assert extra is not shared.browser
        assert extra.is_connected()

        session = open_page(
            SharedBrowser(playwright=shared.playwright, browser=extra),
            _settings(),
            artifacts_dir=tmp_path / "extra",
        )
        session.owns_browser = True
        session.owns_playwright = False
        session.close()

        assert not extra.is_connected()
        assert shared.browser.is_connected()
        # Playwright 仍活：能再开 page
        again = open_page(shared, _settings(), artifacts_dir=tmp_path / "again")
        again.page.goto("about:blank")
        again.close()
    finally:
        shared.close()


def test_isolated_session_close_stops_own_playwright_only(tmp_path: Path) -> None:
    """isolated：关 session 会 stop 自有 Playwright；主 SharedBrowser 仍可用。"""
    from pilot.core.browser import launch_isolated_session

    shared = launch_browser(_settings())
    try:
        session, thr = launch_isolated_session(
            _settings(),
            artifacts_dir=tmp_path / "iso",
        )
        assert session.owns_playwright is True
        thr.call(session.close)
        thr.stop()
        assert shared.browser.is_connected()
        again = open_page(shared, _settings(), artifacts_dir=tmp_path / "again")
        again.page.goto("about:blank")
        again.close()
    finally:
        shared.close()
