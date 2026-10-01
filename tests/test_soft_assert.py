"""软断言：收集失败、with 汇总、禁止嵌套。"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, sync_playwright

from pilot.core import assertx
from pilot.core.config import BrowserSettings
from pilot.core.soft import assert_all, run_assertion, soft_assertions

HTML = """
<html><body>
  <h1 data-testid="title">Hello</h1>
  <div data-testid="ghost" style="display:none">Hidden</div>
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


def test_run_assertion_hard_outside_soft() -> None:
    """with 外：断言失败立即抛出。"""
    with pytest.raises(AssertionError, match="hard-fail"):
        run_assertion(lambda: (_ for _ in ()).throw(AssertionError("hard-fail")))


def test_soft_context_aggregates_and_raises_on_exit() -> None:
    """with 内收集多次失败，退出时一次性抛出。"""
    ran_after = False
    with pytest.raises(AssertionError) as excinfo:
        with soft_assertions():
            run_assertion(lambda: (_ for _ in ()).throw(AssertionError("fail-one")))
            run_assertion(lambda: (_ for _ in ()).throw(AssertionError("fail-two")))
            # 软模式下后续仍可执行
            ran_after = True

    assert ran_after
    message = str(excinfo.value)
    assert "fail-one" in message
    assert "fail-two" in message
    assert "2" in message


def test_soft_context_passes_when_no_failures() -> None:
    """全部通过时 with 安静退出。"""
    with soft_assertions():
        run_assertion(lambda: None)


def test_assert_all_flushes_mid_context() -> None:
    """with 内可提前 assert_all；抛出后收集器清空，后续失败再汇总。"""
    with pytest.raises(AssertionError, match="mid-fail"):
        with soft_assertions():
            run_assertion(lambda: (_ for _ in ()).throw(AssertionError("mid-fail")))
            assert_all()

    # 新的 with 不应残留上次失败
    with soft_assertions():
        run_assertion(lambda: None)


def test_nested_soft_assertions_forbidden() -> None:
    """禁止嵌套 soft_assertions。"""
    with soft_assertions():
        with pytest.raises(RuntimeError, match="[Nn]est"):
            with soft_assertions():
                pass


def test_assertx_expect_soft_inside_context(page: Page) -> None:
    """assertx.expect_* 在 soft 作用域内自动变软并汇总。"""
    title = page.get_by_test_id("title")
    ghost = page.get_by_test_id("ghost")

    with pytest.raises(AssertionError) as excinfo:
        with soft_assertions():
            assertx.expect_text(title, "Wrong", timeout=500)
            assertx.expect_visible(ghost, timeout=500)

    message = str(excinfo.value)
    assert "2" in message


def test_assertx_expect_hard_outside_context(page: Page) -> None:
    """with 外 assertx 仍为硬断言。"""
    with pytest.raises(AssertionError):
        assertx.expect_text(page.get_by_test_id("title"), "Wrong", timeout=500)
