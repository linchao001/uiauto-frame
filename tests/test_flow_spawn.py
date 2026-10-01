"""flow.spawn：单条用例内多用户（多 Context）并存。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pilot.core.browser import launch_browser, open_page
from pilot.core.config import BrowserSettings, PilotConfig
from pilot.flow.base import BaseFlow


class _DemoFlow(BaseFlow):
    """最小产品 Flow，用于验证 spawn 返回同型实例。"""

    marker: str = "root"


def _settings() -> BrowserSettings:
    return BrowserSettings(headless=True, trace="off", video="off")


def test_spawn_without_binding_raises() -> None:
    """未挂到 pytest flow fixture 时，spawn 应明确失败。"""
    flow = _DemoFlow(page=object(), config=PilotConfig())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="spawn"):
        flow.spawn()


def test_spawn_returns_sibling_flow_with_isolated_context(tmp_path: Path) -> None:
    """spawn 在同一 Browser 上新开 Context，返回同型 Flow，互不影响 storage。"""
    shared = launch_browser(_settings())
    sessions: list[Any] = []
    try:
        primary = open_page(shared, _settings(), artifacts_dir=tmp_path / "a")
        sessions.append(primary)

        def open_extra():
            s = open_page(shared, _settings(), artifacts_dir=tmp_path / "b")
            sessions.append(s)
            return s

        def open_browser_unused(*, isolated: bool = False):
            raise RuntimeError("unused")

        def factory(page, config):
            return _DemoFlow(page, config)

        root = factory(primary.page, PilotConfig())
        root.bind_spawner(factory, PilotConfig(), open_extra, open_browser_unused)

        child = root.spawn()
        assert isinstance(child, _DemoFlow)
        assert child is not root
        assert child.page is not root.page
        assert child.page.context is not root.page.context
        assert child.page.context.browser is root.page.context.browser

        # 子 flow 仍可再 spawn（三人场景）
        grandchild = child.spawn()
        assert isinstance(grandchild, _DemoFlow)
        assert grandchild.page.context is not child.page.context
    finally:
        for s in reversed(sessions):
            s.close()
        shared.close()
