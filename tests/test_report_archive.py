"""pytest-html 报告归档与 polish 行为。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pilot.report.archive import (
    artifacts_root_for,
    create_run_dir,
    html_path,
    polish_report_html,
    prepare_html_report,
    read_latest_run_dir,
    sanitize_env_segment,
    timestamp_run_id,
    write_latest_pointer,
)
from pilot.report.html_utils import attach_text, pop_html_extras, pop_steps, step


class _FakeOption:
    def __init__(self, **kwargs):
        self.htmlpath = kwargs.get("htmlpath")
        self.self_contained_html = kwargs.get("self_contained_html", False)
        self.pilot_report = kwargs.get("pilot_report", False)
        self.pilot_report_dir = kwargs.get("pilot_report_dir", "reports")


class _FakeConfig:
    def __init__(self, **kwargs):
        self.option = _FakeOption(**kwargs)


class _FakeItem:
    pass


def test_timestamp_run_id_format():
    assert timestamp_run_id(datetime(2026, 8, 6, 9, 15, 30)) == "20260806_091530"


def test_sanitize_env_segment():
    assert sanitize_env_segment("lab") == "lab"
    assert sanitize_env_segment("../evil") == "evil"
    assert sanitize_env_segment("") == "default"
    assert sanitize_env_segment("a/b") == "b"


def test_create_run_dir_and_latest_pointer(tmp_path: Path):
    root = tmp_path / "reports"
    run = create_run_dir(root, env="lab", run_id="20260806_091530")
    assert run == root / "lab" / "20260806_091530"
    assert run.is_dir()
    assert html_path(run) == run / "report.html"

    write_latest_pointer(run.parent, run)
    latest = read_latest_run_dir(root, env="lab")
    assert latest == run.resolve()
    data = json.loads((root / "lab" / "latest.json").read_text(encoding="utf-8"))
    assert data["run_id"] == "20260806_091530"
    assert data["env"] == "lab"
    assert data["path"] == "20260806_091530"
    assert data["html"] == "report.html"


def test_prepare_html_report_archives_with_report_flag(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = _FakeConfig(
        htmlpath=None,
        pilot_report=True,
        pilot_report_dir=str(tmp_path / "reports"),
    )
    path = prepare_html_report(config, env="lab")
    assert path is not None
    assert path.name == "report.html"
    assert path.parent.parent.name == "lab"
    assert Path(config.option.htmlpath) == path
    assert config.option.self_contained_html is True
    assert read_latest_run_dir(tmp_path / "reports", env="lab") is not None


def test_prepare_html_report_noop_without_report_flag(tmp_path: Path):
    config = _FakeConfig(htmlpath=None, pilot_report=False)
    assert prepare_html_report(config, env="lab") is None
    assert config.option.htmlpath is None
    assert artifacts_root_for(config) is None


def test_artifacts_root_follows_report_run_only(tmp_path: Path):
    """产物目录只解析到本次报告下，且本函数不负责建目录。"""
    config = _FakeConfig(
        htmlpath=None,
        pilot_report=True,
        pilot_report_dir=str(tmp_path / "reports"),
    )
    path = prepare_html_report(config, env="lab")
    assert path is not None
    root = artifacts_root_for(config)
    assert root == path.parent / "artifacts"
    assert not root.exists()


def test_prepare_html_report_keeps_explicit_htmlpath(tmp_path: Path):
    explicit = tmp_path / "custom" / "out.html"
    explicit.parent.mkdir(parents=True)
    config = _FakeConfig(
        htmlpath=str(explicit),
        pilot_report=True,
        pilot_report_dir=str(tmp_path / "reports"),
    )
    assert prepare_html_report(config, env="lab") == explicit
    assert config.option.htmlpath == str(explicit)


def test_polish_report_html_chinese_timestamp(tmp_path: Path):
    path = tmp_path / "report.html"
    path.write_text(
        "<html><body><h1>t</h1>\n"
        "<p>Report generated on 19-Aug-2026 at 15:16:09 by "
        '<a href="https://pypi.python.org/pypi/pytest-html">pytest-html</a>\n'
        "        v4.2.0</p>\n</body></html>\n",
        encoding="utf-8",
    )
    assert polish_report_html(path, when=datetime(2026, 8, 19, 15, 16, 9)) is True
    text = path.read_text(encoding="utf-8")
    assert "报告生成时间：2026-08-19 15:16:09" in text
    assert "pytest-html" not in text
    assert "Report generated" not in text


def test_polish_report_html_injects_ui_shell(tmp_path: Path):
    path = tmp_path / "report.html"
    path.write_text(
        "<html><head><title>r</title></head><body>\n"
        '<div class="summary"><h2>Summary</h2></div>\n'
        '<table id="results-table"></table>\n'
        '<div id="data-container" data-jsonblob="{}"></div>\n'
        "<p>Report generated on 19-Aug-2026 at 15:16:09 by "
        '<a href="https://pypi.python.org/pypi/pytest-html">pytest-html</a> '
        "v4.2.0</p>\n"
        "</body></html>\n",
        encoding="utf-8",
    )
    assert polish_report_html(path, when=datetime(2026, 8, 19, 15, 16, 9)) is True
    text = path.read_text(encoding="utf-8")
    assert 'id="pilot-report-ui"' in text
    assert 'id="pilot-report-ui-css"' in text
    assert 'id="pilot-report-ui-js"' in text
    assert "pilot-overview" in text
    assert polish_report_html(path, when=datetime(2026, 8, 19, 15, 16, 9)) is True
    again = path.read_text(encoding="utf-8")
    assert again.count('id="pilot-report-ui"') == 1


def test_html_extras_queue_and_steps():
    from pilot.report import capture

    item = _FakeItem()
    token = capture.bind_test_item(item)
    try:
        attach_text("hello", name="note")
        with step("do thing"):
            pass
        extras = pop_html_extras(item)
        names = [e.get("name") for e in extras]
        assert "note" in names
        assert pop_steps(item) == [("do thing", "ok", "")]
    finally:
        capture.reset_test_item(token)
