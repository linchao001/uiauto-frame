from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from pilot.core.base_check import BaseCheck
from pilot.core.base_page import BasePage
from pilot.core.config import BrowserSettings

HTML = """
<html><body>
  <h1 data-testid="title">Hello</h1>
  <input data-testid="name" placeholder="Full name" />
  <img alt="logo" title="Brand" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" />
  <p>Visible text node</p>
  <section data-testid="card-1">
    <button>Save</button>
  </section>
  <section data-testid="card-2">
    <button>Save</button>
  </section>
  <button data-testid="item">One</button>
  <button data-testid="item">Two</button>
  <button data-testid="only">Go</button>
</body></html>
"""


@pytest.fixture
def page() -> Page:
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context()
    p = context.new_page()
    p.set_content(HTML)
    try:
        yield p
    finally:
        context.close()
        browser.close()
        pw.stop()


@pytest.fixture
def settings() -> BrowserSettings:
    return BrowserSettings(
        timeout_ms=5_000,
        action_retries=0,
        trace="off",
        screenshot_on_failure=False,
        channel=None,
    )


@pytest.fixture
def home(page: Page, settings: BrowserSettings) -> BasePage:
    return BasePage(page, settings)


@pytest.fixture
def check(page: Page, settings: BrowserSettings) -> BaseCheck:
    return BaseCheck(page, settings)


def test_by_secondary_locators(home: BasePage, check: BaseCheck) -> None:
    check.expect_visible(home.by_placeholder("Full name"))
    check.expect_visible(home.by_alt_text("logo"))
    check.expect_visible(home.by_title("Brand"))
    check.expect_visible(home.by_text("Visible text node"))


def test_click_unique_testid(home: BasePage) -> None:
    home.click("testid:only")


def test_click_strict_fails_on_duplicate_role(home: BasePage) -> None:
    with pytest.raises(PlaywrightError):
        home.click(home.by_role("button", name="Save"))


def test_click_match_first_opt_out(home: BasePage) -> None:
    home.click(home.by_role("button", name="Save"), match="first")


def test_within_narrows_then_click(home: BasePage) -> None:
    home.click(home.within("testid:card-2", "button"))


def test_expect_count_ignores_match_semantics(check: BaseCheck) -> None:
    check.expect_count("testid:item", 2)
