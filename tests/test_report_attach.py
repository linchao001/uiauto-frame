"""失败产物挂到 pytest-html / Allure：收集与可选附件。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pilot.core.report_attach import (
    attach_failure_artifacts,
    collect_failure_artifacts,
    resolve_artifact_dir,
)


def test_resolve_artifact_dir_without_report_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """没开 --report 不回落 cwd artifacts/。"""
    monkeypatch.chdir(tmp_path)
    assert resolve_artifact_dir("test_login") is None
    config = SimpleNamespace()
    assert resolve_artifact_dir("test_login", config=config) is None


def test_resolve_artifact_dir_under_report_run(tmp_path: Path) -> None:
    """开报告时产物跟 report.html 同目录树。"""
    run = tmp_path / "reports" / "lab" / "run"
    config = SimpleNamespace(_pilot_report_run_dir=run)
    assert resolve_artifact_dir("test_login", config=config) == (
        run / "artifacts" / "test_login"
    )


def test_artifact_href_is_relative_to_report(tmp_path: Path) -> None:
    from pilot.core.report_attach import artifact_href

    run = tmp_path / "reports" / "lab" / "run"
    shot = run / "artifacts" / "test_x" / "assert_failure.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"png")
    assert artifact_href(shot, report_dir=run) == "artifacts/test_x/assert_failure.png"


def test_collect_failure_artifacts_finds_png_zip_and_videos(tmp_path: Path) -> None:
    """收集根目录截图/trace，以及 videos 下录像。"""
    (tmp_path / "assert_failure.png").write_bytes(b"png")
    (tmp_path / "soft_1.png").write_bytes(b"png")
    (tmp_path / "trace.zip").write_bytes(b"zip")
    videos = tmp_path / "videos"
    videos.mkdir()
    (videos / "clip.webm").write_bytes(b"vid")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    items = collect_failure_artifacts(tmp_path)
    kinds = {(a.kind, a.path.name) for a in items}
    assert ("image", "assert_failure.png") in kinds
    assert ("image", "soft_1.png") in kinds
    assert ("trace", "trace.zip") in kinds
    assert ("video", "clip.webm") in kinds
    assert all(a.path.name != "notes.txt" for a in items)


def test_collect_failure_artifacts_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert collect_failure_artifacts(tmp_path / "nope") == []


def test_attach_failure_artifacts_html_and_allure(tmp_path: Path) -> None:
    """同时尝试 html extras 与 allure；未安装时跳过对应分支。"""
    png = tmp_path / "assert_failure.png"
    png.write_bytes(b"png")
    z = tmp_path / "trace.zip"
    z.write_bytes(b"zip")

    call_rep = SimpleNamespace(failed=True, extras=[])
    item = SimpleNamespace(name="test_x", rep_call=call_rep)

    html_extra = MagicMock()
    html_extra.html.return_value = "HTML"

    allure_mod = MagicMock()

    with (
        patch("pilot.core.report_attach.resolve_artifact_dir", return_value=tmp_path),
        patch("pilot.core.report_attach._try_import_pytest_html_extras", return_value=html_extra),
        patch("pilot.core.report_attach._try_import_allure", return_value=allure_mod),
        patch("pilot.core.report_attach.ensure_trace_protocol", return_value=True),
    ):
        attach_failure_artifacts(item)

    assert "HTML" in call_rep.extras
    html_extra.html.assert_called()
    allure_mod.attach.file.assert_called()


def test_attach_skips_when_call_not_failed(tmp_path: Path) -> None:
    call_rep = SimpleNamespace(failed=False, extras=[])
    item = SimpleNamespace(name="test_ok", rep_call=call_rep)
    with patch("pilot.core.report_attach.collect_failure_artifacts") as collect:
        attach_failure_artifacts(item)
    collect.assert_not_called()
    assert call_rep.extras == []


def test_attach_noop_without_report_backends(tmp_path: Path) -> None:
    """未装 pytest-html / allure 时不报错。"""
    (tmp_path / "assert_failure.png").write_bytes(b"png")
    call_rep = SimpleNamespace(failed=True, extras=[])
    item = SimpleNamespace(name="test_x", rep_call=call_rep)
    with (
        patch("pilot.core.report_attach.resolve_artifact_dir", return_value=tmp_path),
        patch("pilot.core.report_attach._try_import_pytest_html_extras", return_value=None),
        patch("pilot.core.report_attach._try_import_allure", return_value=None),
    ):
        attach_failure_artifacts(item)
    assert call_rep.extras == []
