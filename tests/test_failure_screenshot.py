"""断言失败即时截图：硬/软断言、无 Page 跳过、开关关闭。"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

from pilot.core.artifacts import ArtifactCollector
from pilot.core.config import BrowserSettings
from pilot.core.failure_capture import (
    bind_failure_capture,
    clear_failure_capture,
    was_assertion_screenshot_taken,
)
from pilot.core.soft import run_assertion, soft_assertions


HTML = """
<html><body>
  <h1 data-testid="title">Hello</h1>
</body></html>
"""


@pytest.fixture
def page() -> Page:
    settings = BrowserSettings(
        browser="chromium",
        channel=None,
        headless=True,
        timeout_ms=2_000,
        trace="off",
        screenshot_on_failure=False,
        video="off",
    )
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=settings.headless)
    context = browser.new_context()
    context.set_default_timeout(settings.timeout_ms)
    p = context.new_page()
    p.set_content(HTML)
    try:
        yield p
    finally:
        context.close()
        browser.close()
        pw.stop()


@pytest.fixture
def artifacts(tmp_path: Path) -> ArtifactCollector:
    return ArtifactCollector(tmp_path)


def test_hard_assertion_captures_screenshot(
    page: Page, artifacts: ArtifactCollector, tmp_path: Path
) -> None:
    """硬断言失败：立即截图，路径写入异常文案。"""
    bind_failure_capture(page, artifacts, enabled=True)
    try:
        with pytest.raises(AssertionError) as excinfo:
            run_assertion(lambda: (_ for _ in ()).throw(AssertionError("hard-boom")))
        assert was_assertion_screenshot_taken() is True
        message = str(excinfo.value)
    finally:
        clear_failure_capture()

    assert "hard-boom" in message
    assert "screenshot:" in message
    shot = tmp_path / "assert_failure.png"
    assert shot.is_file()
    assert str(shot) in message or shot.name in message
    assert was_assertion_screenshot_taken() is False


def test_soft_assertions_capture_numbered_screenshots(
    page: Page, artifacts: ArtifactCollector, tmp_path: Path
) -> None:
    """软断言每条失败各截一张 soft_N.png。"""
    bind_failure_capture(page, artifacts, enabled=True)
    try:
        with pytest.raises(AssertionError) as excinfo:
            with soft_assertions():
                run_assertion(lambda: (_ for _ in ()).throw(AssertionError("soft-a")))
                run_assertion(lambda: (_ for _ in ()).throw(AssertionError("soft-b")))
        assert was_assertion_screenshot_taken() is True
        message = str(excinfo.value)
    finally:
        clear_failure_capture()

    assert "soft-a" in message
    assert "soft-b" in message
    assert (tmp_path / "soft_1.png").is_file()
    assert (tmp_path / "soft_2.png").is_file()
    assert "screenshot:" in message


def test_no_page_bound_skips_screenshot_without_crash(tmp_path: Path) -> None:
    """未绑定 Page 时断言照常失败，不截图、不抛二次异常。"""
    clear_failure_capture()
    with pytest.raises(AssertionError, match="solo"):
        run_assertion(lambda: (_ for _ in ()).throw(AssertionError("solo")))
    assert list(tmp_path.glob("*.png")) == []


def test_disabled_skips_screenshot(
    page: Page, artifacts: ArtifactCollector, tmp_path: Path
) -> None:
    """screenshot_on_failure=False 时不落盘。"""
    bind_failure_capture(page, artifacts, enabled=False)
    try:
        with pytest.raises(AssertionError, match="off"):
            run_assertion(lambda: (_ for _ in ()).throw(AssertionError("off")))
        assert was_assertion_screenshot_taken() is False
    finally:
        clear_failure_capture()
    assert list(tmp_path.glob("*.png")) == []
