"""pilot docs：按任务取 docs/to-agent，以及打进安装包的路径。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from pilot.agent_docs import (
    CATALOG,
    AgentDocsError,
    find_agent_docs,
    iter_markdown,
    render_index,
    render_list,
    render_search,
    render_show,
    resolve_doc,
)
from pilot.cli import main


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_hatch_build():
    path = _repo_root() / "hatch_build.py"
    spec = importlib.util.spec_from_file_location("hatch_build_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_docs(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# 入口\n", encoding="utf-8")
    layers = root / "layers"
    layers.mkdir()
    (layers / "page.md").write_text("wait_ready 必须覆盖\n", encoding="utf-8")


def test_catalog_covers_repo_markdown() -> None:
    root = find_agent_docs()
    on_disk = {path.relative_to(root).as_posix() for path in iter_markdown(root)}
    listed = {topic.path for topic in CATALOG}
    assert on_disk == listed
    assert (root / "config-run.md").is_file()


def test_index_names_show_command() -> None:
    text = render_index(find_agent_docs())
    assert "pilot docs show <id>" in text
    for topic in CATALOG:
        assert topic.id in text
        assert topic.when in text


def test_show_config_alias_and_source_marker() -> None:
    text = render_show("config-run", find_agent_docs())
    assert text.startswith("<!-- docs/to-agent/config-run.md -->")
    assert "product.yaml" in text
    assert "env/<device>.yaml" in text or "env/<device>" in text or "env/" in text


def test_show_page_by_relative_path() -> None:
    text = render_show("layers/page.md", find_agent_docs())
    assert "wait_ready" in text


def test_show_unknown_lists_ids() -> None:
    with pytest.raises(AgentDocsError, match="未知文档") as exc:
        resolve_doc("not-a-doc", find_agent_docs())
    assert "page" in str(exc.value)
    assert "config" in str(exc.value)


def test_resolve_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "to-agent"
    _write_docs(root)
    secret = tmp_path / "secret.md"
    secret.write_text("secret", encoding="utf-8")
    with pytest.raises(AgentDocsError):
        resolve_doc("../secret.md", root)
    with pytest.raises(AgentDocsError):
        resolve_doc(str(secret), root)


def test_show_missing_catalog_file(tmp_path: Path) -> None:
    root = tmp_path / "to-agent"
    root.mkdir()
    (root / "README.md").write_text("# x\n", encoding="utf-8")
    with pytest.raises(AgentDocsError, match="缺失"):
        resolve_doc("page", root)


def test_search_hits_then_miss() -> None:
    root = find_agent_docs()
    text, code = render_search("wait_ready", root, limit=10)
    assert code == 0
    assert "[page]" in text
    assert "layers/page.md" in text
    missed, miss_code = render_search("zzz-no-such-token", root, limit=5)
    assert miss_code == 1
    assert missed.startswith("未找到：")


def test_search_rejects_empty_keyword() -> None:
    with pytest.raises(AgentDocsError, match="关键词为空"):
        render_search("  ", find_agent_docs(), limit=5)


def test_search_per_file_cap(tmp_path: Path) -> None:
    root = tmp_path / "to-agent"
    root.mkdir()
    # 同一词刷很多行，不应占满全部额度
    (root / "README.md").write_text("\n".join(["token"] * 20) + "\n", encoding="utf-8")
    (root / "other.md").write_text("token in other\n", encoding="utf-8")
    text, code = render_search("token", root, limit=30)
    assert code == 0
    assert "[readme]" in text
    assert "other.md" in text
    assert text.count("token") <= 6


def test_find_docs_falls_back_to_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    packaged = tmp_path / "templates" / "to-agent"
    _write_docs(packaged)
    monkeypatch.setattr("pilot.agent_docs.__file__", str(tmp_path / "agent_docs.py"))
    found = find_agent_docs()
    assert found == packaged.resolve()


def test_list_includes_paths() -> None:
    text = render_list(find_agent_docs())
    assert "config" in text
    assert "config-run.md" in text
    assert "layers/page.md" in text


def test_cli_docs_index_and_show(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["docs"]) == 0
    index = capsys.readouterr().out
    assert "pilot docs show" in index
    assert "optional" in index

    assert main(["docs", "show", "api"]) == 0
    shown = capsys.readouterr().out
    assert "api-cheatsheet.md" in shown
    assert "BasePage" in shown


def test_cli_docs_unknown_is_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["docs", "show", "nope"]) == 2
    assert "未知文档" in capsys.readouterr().err


def test_cli_docs_search(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["docs", "search", "product.yaml"]) == 0
    out = capsys.readouterr().out
    assert "[config]" in out


def test_force_include_packs_docs_and_skips_cache(tmp_path: Path) -> None:
    docs = tmp_path / "docs" / "to-agent" / "layers"
    docs.mkdir(parents=True)
    (tmp_path / "docs" / "to-agent" / "README.md").write_text("# 入口\n", encoding="utf-8")
    (docs / "page.md").write_text("# page\n", encoding="utf-8")
    cache = tmp_path / "docs" / "to-agent" / ".pytest_cache"
    cache.mkdir()
    (cache / "note.md").write_text("skip\n", encoding="utf-8")

    mapping = _load_hatch_build().collect_force_include(tmp_path)
    assert mapping["docs/to-agent/README.md"] == "pilot/templates/to-agent/README.md"
    assert mapping["docs/to-agent/layers/page.md"] == "pilot/templates/to-agent/layers/page.md"
    assert not any(".pytest_cache" in key for key in mapping)


def test_force_include_from_sdist_layout(tmp_path: Path) -> None:
    """sdist 里没有 docs/，只有已经搬进 pilot/templates 的文件。"""
    docs = tmp_path / "pilot" / "templates" / "to-agent"
    docs.mkdir(parents=True)
    (docs / "README.md").write_text("# 入口\n", encoding="utf-8")
    (docs / "config-run.md").write_text("# 配置\n", encoding="utf-8")

    mapping = _load_hatch_build().collect_force_include(tmp_path)
    readme_key = "pilot/templates/to-agent/README.md"
    config_key = "pilot/templates/to-agent/config-run.md"
    assert mapping[readme_key] == readme_key
    assert mapping[config_key] == config_key


def test_repo_force_include_covers_shipped_docs() -> None:
    mapping = _load_hatch_build().collect_force_include(_repo_root())
    assert mapping["docs/to-agent/README.md"] == "pilot/templates/to-agent/README.md"
    assert mapping["docs/to-agent/config-run.md"] == "pilot/templates/to-agent/config-run.md"
    assert not any("templates/demo" in key for key in mapping)
