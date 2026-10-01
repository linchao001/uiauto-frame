"""失败产物可选挂到 pytest-html / Allure（未安装则静默跳过）。"""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pilot.core.logging import get_logger
from pilot.report.archive import artifacts_root_for, report_run_dir
from pilot.report.trace_protocol import ensure_trace_protocol, trace_open_href

logger = get_logger("pilot")

ArtifactKind = Literal["image", "trace", "video"]

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_VIDEO_SUFFIXES = {".webm", ".mp4"}
_TRACE_SUFFIXES = {".zip"}


@dataclass(frozen=True)
class FailureArtifact:
    """一条待挂载的失败产物。"""

    kind: ArtifactKind
    path: Path


def resolve_artifact_dir(
    node_name: str,
    *,
    results_root: Path | None = None,
    config: Any | None = None,
) -> Path | None:
    """解析用例产物目录：仅报告运行时为 ``<报告目录>/artifacts/<node>``。"""
    if results_root is not None:
        return Path(results_root) / node_name
    if config is None:
        return None
    root = artifacts_root_for(config)
    if root is None:
        return None
    return root / node_name


def artifact_href(path: Path, *, report_dir: Path | None) -> str:
    """相对 report.html 的链接；无法相对化时退回绝对 posix 路径。"""
    resolved = path.resolve()
    if report_dir is not None:
        try:
            return resolved.relative_to(Path(report_dir).resolve()).as_posix()
        except ValueError:
            pass
    return resolved.as_posix()


def collect_failure_artifacts(root: Path) -> list[FailureArtifact]:
    """扫描产物目录：根下截图/trace.zip，以及 videos/ 下录像。"""
    if not root.is_dir():
        return []

    items: list[FailureArtifact] = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in _IMAGE_SUFFIXES:
            items.append(FailureArtifact("image", path))
        elif suffix in _TRACE_SUFFIXES:
            items.append(FailureArtifact("trace", path))

    videos = root / "videos"
    if videos.is_dir():
        for path in sorted(videos.rglob("*")):
            if path.is_file() and path.suffix.lower() in _VIDEO_SUFFIXES:
                items.append(FailureArtifact("video", path))

    return items


def _try_import_pytest_html_extras() -> Any | None:
    """导入 pytest-html 的 extras API。"""
    try:
        from pytest_html import extras  # type: ignore[import-untyped]
    except ImportError:
        return None
    return extras


def _try_import_allure() -> Any | None:
    """导入 allure-pytest。"""
    try:
        import allure  # type: ignore[import-untyped]
    except ImportError:
        return None
    return allure


def _allure_type(allure: Any, kind: ArtifactKind) -> Any:
    """映射到 allure attachment type；无枚举时回退 MIME 字符串。"""
    attachment_type = getattr(allure, "attachment_type", None)
    if attachment_type is not None:
        if kind == "image":
            return attachment_type.PNG
        if kind == "video":
            return getattr(attachment_type, "WEBM", "video/webm")
        return getattr(attachment_type, "ZIP", "application/zip")
    if kind == "image":
        return "image/png"
    if kind == "video":
        return "video/webm"
    return "application/zip"


def _clickable_html(href: str, name: str, *, image: bool) -> str:
    """相对路径链接；图片可点开新标签查看。"""
    safe_href = html.escape(href, quote=True)
    safe_name = html.escape(name)
    if image:
        return (
            f'<a class="pilot-shot-link" href="{safe_href}" target="_blank" '
            f'rel="noopener">{safe_name}'
            f'<br/><img src="{safe_href}" alt="{safe_name}" '
            f'style="max-width:100%;max-height:280px;margin-top:6px"/></a>'
        )
    return (
        f'<a class="pilot-shot-link" href="{safe_href}" target="_blank" '
        f'rel="noopener">{safe_name}</a>'
    )


def _trace_link_html(path: Path) -> str:
    """Trace 用自定义协议打开 Viewer，不把 zip 当普通下载链接。"""
    open_href = html.escape(trace_open_href(path), quote=True)
    return (
        f'<a class="pilot-shot-link" href="{open_href}" '
        f'title="打开 Trace Viewer；首次点击时浏览器会询问是否允许">'
        f"打开 Trace</a>"
    )


def _attach_html(
    report: Any,
    artifacts: list[FailureArtifact],
    extras: Any,
    *,
    report_dir: Path | None,
) -> None:
    """把产物写成相对 report.html 的可点击链接（不内联绝对路径）。"""
    if any(art.kind == "trace" for art in artifacts):
        # 同一次运行里注册协议，报告里的链接才能点开本机 Viewer
        ensure_trace_protocol()
    bucket = list(getattr(report, "extras", []) or [])
    for art in artifacts:
        if art.kind == "trace":
            snippet = _trace_link_html(art.path)
        else:
            href = artifact_href(art.path, report_dir=report_dir)
            snippet = _clickable_html(href, art.path.name, image=art.kind == "image")
        bucket.append(extras.html(snippet))
    report.extras = bucket


def _attach_allure(artifacts: list[FailureArtifact], allure: Any) -> None:
    """Allure 即时附件；与 HTML 独立，互不影响。"""
    for art in artifacts:
        try:
            allure.attach.file(
                str(art.path.resolve()),
                name=art.path.name,
                attachment_type=_allure_type(allure, art.kind),
            )
        except Exception as exc:  # noqa: BLE001 - 报告附加失败不应掩盖用例结果
            logger.warning("Allure attach failed for %s: %s", art.path, exc)


def attach_failure_artifacts(item: Any, *, results_root: Path | None = None) -> None:
    """若 call 失败，把报告目录下 artifacts/<name>/ 产物挂到 html/allure。

    应在 fixture teardown 之后调用（通常在 makereport ``teardown`` 阶段），
    以便截图兜底与 trace.zip 已落盘；附件写回 ``item.rep_call.extras``。
    """
    call_rep = getattr(item, "rep_call", None)
    if call_rep is None or not getattr(call_rep, "failed", False):
        return

    node_name = getattr(item, "name", None)
    if not node_name:
        return

    config = getattr(item, "config", None)
    root = resolve_artifact_dir(
        str(node_name), results_root=results_root, config=config
    )
    if root is None:
        return
    artifacts = collect_failure_artifacts(root)
    if not artifacts:
        return

    extras = _try_import_pytest_html_extras()
    if extras is not None:
        try:
            _attach_html(
                call_rep,
                artifacts,
                extras,
                report_dir=report_run_dir(config) if config is not None else None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pytest-html extras attach failed: %s", exc)

    allure = _try_import_allure()
    if allure is not None:
        _attach_allure(artifacts, allure)
