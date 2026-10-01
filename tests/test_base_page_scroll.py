"""BasePage.scroll_into_view 行为测试。"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, sync_playwright

from pilot.core.base_page import BasePage
from pilot.core.config import BrowserSettings

# 页面级长页 + 嵌套滚动容器；目标初始在视口/容器外
HTML = """
<html><body style="margin:0">
  <div style="height:2000px"></div>
  <a data-testid="footer-link" href="#">Footer</a>
  <div data-testid="scroll-box"
       style="height:120px; overflow:auto; border:1px solid #000; margin-top:40px">
    <div style="height:400px"></div>
    <button data-testid="deep-item">Deep</button>
    <button data-testid="deep-item">Also</button>
  </div>
</body></html>
"""


def _in_viewport(locator: Locator) -> bool:
    """判断元素是否与视口相交（用于断言滚入可见）。"""
    return bool(
        locator.evaluate(
            """el => {
              const r = el.getBoundingClientRect();
              return r.bottom > 0 && r.top < window.innerHeight
                && r.right > 0 && r.left < window.innerWidth;
            }"""
        )
    )


def _in_container(child: Locator, container: Locator) -> bool:
    """判断子元素是否与滚动容器可视区域相交。"""
    return bool(
        child.evaluate(
            """(el, box) => {
              const r = el.getBoundingClientRect();
              const c = box.getBoundingClientRect();
              return r.bottom > c.top && r.top < c.bottom
                && r.right > c.left && r.left < c.right;
            }""",
            container.element_handle(),
        )
    )


@pytest.fixture
def page() -> Page:
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 800, "height": 600})
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


def test_scroll_into_view_brings_page_target_into_viewport(home: BasePage) -> None:
    target = home.by_testid("footer-link")
    assert not _in_viewport(target)

    home.scroll_into_view("testid:footer-link")

    assert _in_viewport(target)


def test_scroll_into_view_nested_container_via_within(home: BasePage) -> None:
    box = home.by_testid("scroll-box")
    deep = home.within("testid:scroll-box", "testid:deep-item")
    # strict 下两个 deep-item 会失败，先用 first 验证容器滚动本身
    home.scroll_into_view(deep, match="first")

    assert _in_container(home.nth("testid:deep-item", 0), box)


def test_scroll_into_view_strict_fails_on_duplicate(home: BasePage) -> None:
    with pytest.raises(PlaywrightError):
        home.scroll_into_view(home.within("testid:scroll-box", "testid:deep-item"))
