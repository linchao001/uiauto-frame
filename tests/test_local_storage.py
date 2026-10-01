"""pilot.core.storage：向页面写入 localStorage。"""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

from pilot.core.storage import install_local_storage, set_local_storage


def test_set_local_storage_writes_json_string() -> None:
    """在已建立 origin 的页面上写入 localStorage。"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        # data URL 无稳定 origin；用 about:blank 后 goto 本地空页不可靠，改用示例站
        page.goto("https://example.com")
        # 中性假 payload：只验证 JSON 字符串能完整读写
        payload = {"session": "abc", "ttl": 3600}
        set_local_storage(page, {"app.session": json.dumps(payload, ensure_ascii=False)})
        raw = page.evaluate("() => localStorage.getItem('app.session')")
        assert json.loads(raw)["session"] == "abc"
        browser.close()


def test_install_local_storage_before_navigation() -> None:
    """init script 在首屏脚本前写入，导航后即可读到。"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        install_local_storage(context, {"app.session": json.dumps({"session": "pre"})})
        page = context.new_page()
        page.goto("https://example.com")
        raw = page.evaluate("() => localStorage.getItem('app.session')")
        assert json.loads(raw)["session"] == "pre"
        browser.close()
