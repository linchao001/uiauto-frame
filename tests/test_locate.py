from __future__ import annotations

import pytest
from playwright.sync_api import Page, sync_playwright

from pilot.core import locate

HTML = """
<html><body>
  <section data-testid="row-a">
    <button data-testid="edit">Edit A</button>
  </section>
  <section data-testid="row-b">
    <button data-testid="edit">Edit B</button>
  </section>
  <button>Alpha</button>
  <button>Beta</button>
  <ul>
    <li>one</li>
    <li>two</li>
    <li>three</li>
  </ul>
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


def test_resolve_testid_and_css_and_locator(page: Page) -> None:
    assert locate.resolve(page, "testid:row-a").get_attribute("data-testid") == "row-a"
    assert locate.resolve(page, "ul li").count() == 3
    existing = page.get_by_test_id("row-b")
    assert locate.resolve(page, existing) is existing


def test_apply_match_first_last_nth(page: Page) -> None:
    buttons = page.locator("body > button")
    assert locate.apply_match(buttons, "first").inner_text() == "Alpha"
    assert locate.apply_match(buttons, "last").inner_text() == "Beta"
    assert locate.apply_match(page.locator("ul li"), 1).inner_text() == "two"
    assert locate.apply_match(buttons, "strict") is buttons


def test_apply_match_rejects_invalid(page: Page) -> None:
    loc = page.get_by_role("button")
    with pytest.raises(ValueError):
        locate.apply_match(loc, "second")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        locate.apply_match(loc, -1)


def test_within_scopes_child(page: Page) -> None:
    root = locate.resolve(page, "testid:row-b")
    child = locate.within(root, "testid:edit")
    assert child.inner_text() == "Edit B"


def test_filter_has_text_and_nth(page: Page) -> None:
    items = page.locator("ul li")
    assert locate.filter_has_text(items, "two").inner_text() == "two"
    assert locate.nth(items, 0).inner_text() == "one"
