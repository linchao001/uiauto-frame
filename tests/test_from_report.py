"""--from-report：解析 pytest-html，只保留 Failed/Error 的 nodeid。"""

from __future__ import annotations

import html as html_lib
import json
from pathlib import Path

import pytest

from pilot.report.from_report import (
    FromReportError,
    deselect_not_in_report,
    extract_failed_nodeids,
    normalize_nodeid,
    resolve_report_html_path,
)


def _make_report_html(tests: dict) -> str:
    """构造含 data-jsonblob 的最小 pytest-html 报告。"""
    blob = html_lib.escape(json.dumps({"tests": tests}, ensure_ascii=False), quote=True)
    return (
        "<!DOCTYPE html><html><body>"
        f'<div id="data-container" data-jsonblob="{blob}"></div>'
        "</body></html>"
    )


class _FakeItem:
    def __init__(self, nodeid: str):
        self.nodeid = nodeid


def test_normalize_nodeid_strips_phase_and_slashes() -> None:
    assert (
        normalize_nodeid(r"SMA\WEB\test_a.py::test_foo::call")
        == "SMA/WEB/test_a.py::test_foo"
    )
    assert normalize_nodeid("a/b.py::Test::test_x::setup") == "a/b.py::Test::test_x"
    assert normalize_nodeid("a/b.py::test_y::teardown") == "a/b.py::test_y"
    assert normalize_nodeid("a/b.py::test_z") == "a/b.py::test_z"


def test_resolve_report_html_path_file_and_dir(tmp_path: Path) -> None:
    html = tmp_path / "report.html"
    html.write_text("<html></html>", encoding="utf-8")
    assert resolve_report_html_path(html) == html.resolve()
    assert resolve_report_html_path(tmp_path) == html.resolve()


def test_resolve_report_html_path_missing(tmp_path: Path) -> None:
    with pytest.raises(FromReportError, match="not found"):
        resolve_report_html_path(tmp_path / "missing.html")


def test_extract_failed_nodeids_failed_and_error_only(tmp_path: Path) -> None:
    tests = {
        "pkg/test_a.py::test_pass": [
            {"result": "Passed", "testId": "pkg/test_a.py::test_pass"}
        ],
        "pkg/test_b.py::test_fail": [
            {"result": "Failed", "testId": "pkg/test_b.py::test_fail::call"}
        ],
        "pkg/test_c.py::test_err": [
            {"result": "Error", "testId": "pkg/test_c.py::test_err::setup"}
        ],
        "pkg/test_d.py::test_skip": [
            {"result": "Skipped", "testId": "pkg/test_d.py::test_skip"}
        ],
    }
    path = tmp_path / "report.html"
    path.write_text(_make_report_html(tests), encoding="utf-8")
    got = extract_failed_nodeids(path)
    assert got == {
        "pkg/test_b.py::test_fail",
        "pkg/test_c.py::test_err",
    }


def test_extract_failed_nodeids_empty_raises(tmp_path: Path) -> None:
    tests = {
        "pkg/test_a.py::test_pass": [
            {"result": "Passed", "testId": "pkg/test_a.py::test_pass"}
        ],
    }
    path = tmp_path / "report.html"
    path.write_text(_make_report_html(tests), encoding="utf-8")
    with pytest.raises(FromReportError, match="no failed|no error"):
        extract_failed_nodeids(path)


def test_extract_failed_nodeids_bad_html(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    path.write_text("<html><body>no blob</body></html>", encoding="utf-8")
    with pytest.raises(FromReportError, match="data-jsonblob"):
        extract_failed_nodeids(path)


def test_deselect_not_in_report_keeps_matches() -> None:
    wanted = {"pkg/test_b.py::test_fail", "pkg/test_c.py::test_err"}
    items = [
        _FakeItem("pkg/test_a.py::test_pass"),
        _FakeItem("pkg/test_b.py::test_fail"),
        _FakeItem(r"pkg\test_c.py::test_err"),
    ]
    kept, deselected = deselect_not_in_report(items, wanted)  # type: ignore[arg-type]
    assert [i.nodeid for i in kept] == [
        "pkg/test_b.py::test_fail",
        r"pkg\test_c.py::test_err",
    ]
    assert [i.nodeid for i in deselected] == ["pkg/test_a.py::test_pass"]


def test_deselect_not_in_report_none_matched_raises() -> None:
    wanted = {"pkg/missing.py::test_x"}
    items = [_FakeItem("pkg/test_a.py::test_pass")]
    with pytest.raises(FromReportError, match="none of the failed"):
        deselect_not_in_report(items, wanted)  # type: ignore[arg-type]
