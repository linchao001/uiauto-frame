"""按次归档 pytest-html：``reports/<env>/<timestamp>/report.html``。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_REPORT_ROOT = "reports"
LATEST_POINTER = "latest.json"
HTML_FILENAME = "report.html"
ARTIFACTS_DIRNAME = "artifacts"
DEFAULT_ENV_SEGMENT = "default"
_RESOURCES = Path(__file__).resolve().parent / "resources"
REPORT_CSS = _RESOURCES / "report.css"
REPORT_JS = _RESOURCES / "report.js"

# pytest-html 默认页脚（见其 index.jinja2）
_PYTEST_HTML_GENERATED_RE = re.compile(
    r"<p>Report generated on .+? by "
    r'<a href="https://pypi\.python\.org/pypi/pytest-html">pytest-html</a>'
    r"\s*v[\d.]+</p>",
    re.DOTALL,
)
# 增强报告 UI 壳：注入 / 幂等替换时按这些 id 匹配
_UI_STYLE_RE = re.compile(
    r'\s*<style[^>]*\bid="pilot-report-ui-css"[^>]*>.*?</style>',
    re.DOTALL | re.IGNORECASE,
)
_UI_SCRIPT_RE = re.compile(
    r'\s*<script[^>]*\bid="pilot-report-ui-js"[^>]*>.*?</script>',
    re.DOTALL | re.IGNORECASE,
)
_UI_DIV_RE = re.compile(
    r'\s*<div[^>]*\bid="pilot-report-ui"[^>]*>\s*</div>',
    re.IGNORECASE,
)


def _inject_report_ui(text: str) -> str:
    """嵌入总览 / 主从详情 CSS+JS 壳（幂等替换）。"""
    css = REPORT_CSS.read_text(encoding="utf-8") if REPORT_CSS.is_file() else ""
    js = REPORT_JS.read_text(encoding="utf-8") if REPORT_JS.is_file() else ""

    cleaned = _UI_STYLE_RE.sub("", text)
    cleaned = _UI_SCRIPT_RE.sub("", cleaned)
    cleaned = _UI_DIV_RE.sub("", cleaned)

    style_tag = (
        f'<style type="text/css" id="pilot-report-ui-css">\n{css}\n</style>\n'
    )
    if re.search(r"</head\s*>", cleaned, re.IGNORECASE):
        cleaned = re.sub(
            r"</head\s*>",
            style_tag + "</head>",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        cleaned = style_tag + cleaned

    body_inject = (
        '<div id="pilot-report-ui"></div>\n'
        f'<script id="pilot-report-ui-js">\n{js}\n</script>\n'
    )
    body_match = None
    for m in re.finditer(r"</body\s*>", cleaned, flags=re.IGNORECASE):
        body_match = m
    if body_match is not None:
        i = body_match.start()
        cleaned = cleaned[:i] + body_inject + cleaned[i:]
    else:
        cleaned = cleaned + body_inject
    return cleaned


def polish_report_html(path: Path | str, *, when: datetime | None = None) -> bool:
    """中文页脚 + 注入报告总览壳；已写入 UI 壳时返回 True。"""
    html_file = Path(path)
    if not html_file.is_file():
        return False
    text = html_file.read_text(encoding="utf-8")
    stamp = (when or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    replacement = f"<p>报告生成时间：{stamp}</p>"
    new_text, _count = _PYTEST_HTML_GENERATED_RE.subn(replacement, text, count=1)
    new_text = _inject_report_ui(new_text)
    if new_text != text:
        html_file.write_text(new_text, encoding="utf-8")
    return 'id="pilot-report-ui"' in new_text


def timestamp_run_id(when: datetime | None = None) -> str:
    """生成 ``YYYYMMDD_HHMMSS`` 运行目录名。"""
    when = when or datetime.now()
    return when.strftime("%Y%m%d_%H%M%S")


def sanitize_env_segment(env: str | None) -> str:
    """把 env 名收成单层路径段，避免目录穿越。"""
    raw = (env or "").strip()
    if not raw:
        return DEFAULT_ENV_SEGMENT
    name = Path(raw.replace("\\", "/")).name.strip()
    if name in ("", ".", ".."):
        return DEFAULT_ENV_SEGMENT
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in name)
    return safe or DEFAULT_ENV_SEGMENT


def create_run_dir(
    report_root: Path | str,
    *,
    env: str | None = None,
    run_id: str | None = None,
) -> Path:
    """创建 ``<report_root>/<env>/<run_id>/`` 并返回。"""
    root = Path(report_root)
    env_dir = root / sanitize_env_segment(env)
    run_dir = env_dir / (run_id or timestamp_run_id())
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def html_path(run_dir: Path | str) -> Path:
    """run 目录下的 ``report.html`` 路径。"""
    return Path(run_dir) / HTML_FILENAME


def write_latest_pointer(pointer_root: Path | str, run_dir: Path | str) -> Path:
    """在 ``pointer_root``（通常 ``reports/<env>/``）写 ``latest.json``。"""
    root = Path(pointer_root).resolve()
    run = Path(run_dir).resolve()
    try:
        rel = run.relative_to(root).as_posix()
    except ValueError:
        rel = str(run)
    pointer = root / LATEST_POINTER
    root.mkdir(parents=True, exist_ok=True)
    pointer.write_text(
        json.dumps(
            {
                "run_id": run.name,
                "env": root.name,
                "path": rel,
                "absolute": str(run),
                "html": HTML_FILENAME,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return pointer


def read_latest_run_dir(
    report_root: Path | str | None = None,
    *,
    env: str | None = None,
) -> Path | None:
    """读 ``latest.json`` 指向的最近一次 run 目录。"""
    root = Path(report_root or DEFAULT_REPORT_ROOT)
    if env is not None:
        pointer_root = root / sanitize_env_segment(env)
    elif (root / LATEST_POINTER).is_file():
        pointer_root = root
    else:
        pointer_root = root / DEFAULT_ENV_SEGMENT

    pointer = pointer_root / LATEST_POINTER
    if not pointer.is_file():
        return None
    data: dict[str, Any] = json.loads(pointer.read_text(encoding="utf-8"))
    rel = data.get("path") or data.get("run_id")
    if not rel:
        return None
    candidate = Path(rel)
    if not candidate.is_absolute():
        candidate = pointer_root / candidate
    return candidate if candidate.is_dir() else None


def _ensure_report_css(config: Any) -> None:
    """把报告 CSS 追加到 pytest-html 的 ``--css``，供 Title 悬停样式。"""
    if not REPORT_CSS.is_file():
        return
    path = str(REPORT_CSS)
    existing = list(getattr(config.option, "css", None) or [])
    if path not in existing:
        existing.append(path)
    config.option.css = existing


def report_run_dir(config: Any) -> Path | None:
    """``--report`` 时的本次归档目录（report.html 所在目录）；否则 None。"""
    run_dir = getattr(config, "_pilot_report_run_dir", None)
    return Path(run_dir) if run_dir is not None else None


def artifacts_root_for(config: Any) -> Path | None:
    """失败产物根目录：仅 ``--report`` 时为 ``<run>/artifacts``；否则不落盘。"""
    run_dir = report_run_dir(config)
    if run_dir is None:
        return None
    return run_dir / ARTIFACTS_DIRNAME


def prepare_html_report(config: Any, *, env: str | None = None) -> Path | None:
    """``--report`` 时归档到 ``reports/<env>/<timestamp>/``。"""
    if not getattr(config.option, "pilot_report", False):
        return None
    if not hasattr(config.option, "htmlpath"):
        return None

    report_root = Path(
        getattr(config.option, "pilot_report_dir", None) or DEFAULT_REPORT_ROOT
    )
    env_name = sanitize_env_segment(env)
    _ensure_report_css(config)

    if config.option.htmlpath:
        # 显式 ``--html``：仍记录归档元数据（若落在 run 目录下）
        path = Path(config.option.htmlpath)
        run_dir = path.parent
        pointer_root = (
            run_dir.parent if run_dir.parent != run_dir else report_root / env_name
        )
        config._pilot_report_run_dir = run_dir  # type: ignore[attr-defined]
        config._pilot_report_root = report_root  # type: ignore[attr-defined]
        config._pilot_report_pointer_root = pointer_root  # type: ignore[attr-defined]
        write_latest_pointer(pointer_root, run_dir)
        return path

    run_dir = create_run_dir(report_root, env=env_name)
    path = html_path(run_dir)
    config.option.htmlpath = str(path)
    # 离线单文件：样式/脚本/图片内联
    if hasattr(config.option, "self_contained_html"):
        config.option.self_contained_html = True
    pointer_root = run_dir.parent
    config._pilot_report_run_dir = run_dir  # type: ignore[attr-defined]
    config._pilot_report_root = report_root  # type: ignore[attr-defined]
    config._pilot_report_pointer_root = pointer_root  # type: ignore[attr-defined]
    write_latest_pointer(pointer_root, run_dir)
    return path


def finalize_report_archive(config: Any) -> Path | None:
    """pytest-html 写完后刷新 latest 指针并 polish 页脚/UI。"""
    run_dir: Path | None = getattr(config, "_pilot_report_run_dir", None)
    if run_dir is None:
        return None
    pointer_root: Path | None = getattr(config, "_pilot_report_pointer_root", None)
    if pointer_root is None:
        pointer_root = run_dir.parent
    write_latest_pointer(pointer_root, run_dir)
    polish_report_html(html_path(run_dir))
    return run_dir
