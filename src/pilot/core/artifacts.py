"""Failure artifacts: screenshots and Playwright traces."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pilot.core.logging import get_logger

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = get_logger("pilot")


class ArtifactCollector:
    """失败截图 / trace 落盘。``report_dir`` 为 report.html 所在目录时，链接用相对路径。"""

    def __init__(
        self,
        root: str | Path = "artifacts",
        *,
        report_dir: str | Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.report_dir = Path(report_dir) if report_dir is not None else None

    def link_for(self, path: Path) -> str:
        """报告内可点击的路径：优先相对 report.html。"""
        resolved = path.resolve()
        if self.report_dir is not None:
            try:
                return resolved.relative_to(self.report_dir.resolve()).as_posix()
            except ValueError:
                pass
        return resolved.as_posix()

    def screenshot(self, page: Page, name: str) -> Path | None:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:120]
        path = self.root / f"{safe}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            logger.info("Screenshot saved: %s", path)
            return path
        except Exception as exc:  # noqa: BLE001 - best effort on failure path
            logger.warning("Failed to capture screenshot: %s", exc)
            return None

    def path_for(self, name: str, suffix: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:120]
        path = self.root / f"{safe}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
