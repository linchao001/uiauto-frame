"""浏览器存储辅助：写入 localStorage（接口登录后注入会话）。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page


def set_local_storage(page: Page, items: dict[str, str]) -> None:
    """向当前页 origin 写入 localStorage。

    ``items`` 的 value 须已是字符串（对象请先 ``json.dumps``）。
    调用前页面须已导航到目标站点 origin（否则无法写同域存储）。
    """
    if not items:
        return
    page.evaluate(
        """(entries) => {
            for (const [key, value] of Object.entries(entries)) {
                localStorage.setItem(key, value);
            }
        }""",
        items,
    )


def install_local_storage(context: BrowserContext, items: dict[str, str]) -> None:
    """在每次导航的页面脚本执行前写入 localStorage。

    适合接口登录：避免 SPA 启动时用空 token 覆盖后写的值。
    """
    if not items:
        return
    serialized = json.dumps(items, ensure_ascii=False)
    context.add_init_script(
        f"""(() => {{
            const entries = {serialized};
            for (const [key, value] of Object.entries(entries)) {{
                localStorage.setItem(key, value);
            }}
        }})();"""
    )


def ensure_origin(page: Page, base_url: str) -> None:
    """打开站点根路径以建立 origin，便于随后写 localStorage。"""
    root = base_url.rstrip("/") + "/"
    page.goto(root, wait_until="domcontentloaded")
