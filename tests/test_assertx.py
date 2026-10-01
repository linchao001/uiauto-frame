from __future__ import annotations

import pytest
from playwright.sync_api import Page, sync_playwright

from pilot.core import assertx
from pilot.core.base_check import BaseCheck
from pilot.core.config import BrowserSettings

HTML = """
<html><body>
  <h1 data-testid="title">Hello</h1>
  <input data-testid="name" value="Alice" data-role="user" />
  <button data-testid="item">One</button>
  <button data-testid="item">Two</button>
  <div data-testid="ghost" style="display:none">Hidden</div>
</body></html>
"""


@pytest.fixture
def page() -> Page:
    settings = BrowserSettings(
        browser="chromium",
        channel=None,
        headless=True,
        timeout_ms=5_000,
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


def test_assertx_expect_visible_and_text(page: Page) -> None:
    title = page.get_by_test_id("title")
    assertx.expect_visible(title, timeout=5_000)
    assertx.expect_text(title, "Hello", timeout=5_000)


def test_assertx_expect_value_attribute_count_hidden(page: Page) -> None:
    assertx.expect_value(page.get_by_test_id("name"), "Alice", timeout=5_000)
    assertx.expect_attribute(page.get_by_test_id("name"), "data-role", "user", timeout=5_000)
    assertx.expect_count(page.get_by_test_id("item"), 2, timeout=5_000)
    assertx.expect_hidden(page.get_by_test_id("ghost"), timeout=5_000)


def test_assertx_expect_url_contains(page: Page) -> None:
    page.goto("data:text/html,<html><body>ok</body></html>")
    assertx.expect_url_contains(page, "data:text/html", timeout=5_000)


@pytest.fixture
def settings() -> BrowserSettings:
    return BrowserSettings(timeout_ms=5_000, trace="off", channel=None)


def test_base_check_expect_delegates_and_count_without_first(
    page: Page, settings: BrowserSettings
) -> None:
    check = BaseCheck(page, settings)
    check.expect_visible("testid:title")
    check.expect_text("testid:title", "Hello")
    check.expect_value("testid:name", "Alice")
    check.expect_attribute("testid:name", "data-role", "user")
    check.expect_hidden("testid:ghost")
    # Critical: two nodes share testid item — must count 2 (no .first)
    check.expect_count("testid:item", 2)


def test_base_check_expect_url_contains(page: Page, settings: BrowserSettings) -> None:
    page.goto("data:text/html,<html><body>ok</body></html>")
    BaseCheck(page, settings).expect_url_contains("data:text/html")


def test_base_check_db_forward(settings: BrowserSettings, page: Page) -> None:
    """DB 断言经 BaseCheck 转发 assertx，用法与 UI expect 统一为 self.expect_*。"""
    check = BaseCheck(page, settings)
    check.expect_row({"id": 1, "name": "a"}, {"name": "a"})
    check.expect_rows_count([{"id": 1}], 1)
