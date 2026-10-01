"""查询打包进框架的 Agent 文档（``docs/to-agent``）。

安装后用 ``pilot docs`` 取索引，再用 ``pilot docs show <id>`` 只读一篇，
避免把整目录塞进上下文。源码 / editable 优先仓库里的 ``docs/to-agent``，
否则用 wheel 里的 ``pilot/templates/to-agent``。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pilot.scaffold import SKIP_DIR_NAMES

# 与 docs/to-agent/README.md 阅读表一致。改表时两边一起改。
# id 给 CLI；path 是文档根下的相对路径；aliases 兼容文件名。


@dataclass(frozen=True)
class DocTopic:
    """一篇给 Agent 的专题：短 id、相对路径、何时该读。"""

    id: str
    path: str
    when: str
    aliases: tuple[str, ...] = ()


CATALOG: tuple[DocTopic, ...] = (
    DocTopic("readme", "README.md", "硬规则、分层、最小步骤（写用例前先读）"),
    DocTopic("page", "layers/page.md", "页面定位 / 操作 / wait_ready"),
    DocTopic("action", "layers/action.md", "业务 Actions / Flow 组装"),
    DocTopic("check", "layers/check.md", "业务断言 / soft"),
    DocTopic("case", "layers/case.md", "写 cases/ 用例"),
    DocTopic(
        "config",
        "config-run.md",
        "用例仓库配置（设备、字段、账号）",
        ("config-run",),
    ),
    DocTopic(
        "api",
        "api-cheatsheet.md",
        "方法名或 import 不确定",
        ("api-cheatsheet", "cheatsheet"),
    ),
    DocTopic("optional", "optional.md", "DB / SSH / @cases / 飞书 / 报告"),
)

# 单篇最多几条，避免一个词全挤在同一文件，Agent 看不到其他文档
_SEARCH_PER_FILE = 5
_LINE_WIDTH = 200


class AgentDocsError(RuntimeError):
    """文档根缺失、id 未知或查询非法。"""


def is_agent_docs_root(path: Path) -> bool:
    """文档根至少要有入口 README，避免误认别的 docs 目录。"""
    return (path / "README.md").is_file()


def find_agent_docs() -> Path:
    """定位 ``docs/to-agent``。

    优先沿当前模块向上找仓库（源码 / editable）。
    找不到再用打进安装包的 ``pilot/templates/to-agent``。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        docs = parent / "docs" / "to-agent"
        if is_agent_docs_root(docs):
            return docs
    packaged = here.parent / "templates" / "to-agent"
    if is_agent_docs_root(packaged):
        return packaged
    raise AgentDocsError(
        "找不到 docs/to-agent。请安装带文档的 pilot-framework，或在框架仓库中运行。"
    )


def iter_markdown(root: Path) -> list[Path]:
    """按阅读表顺序列出 markdown。未编入索引的文件排在后面。"""
    ordered: list[Path] = []
    seen: set[Path] = set()
    for topic in CATALOG:
        path = root / topic.path
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        ordered.append(path)
        seen.add(resolved)
    extras: list[Path] = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        resolved = path.resolve()
        if resolved in seen or not path.is_file():
            continue
        extras.append(path)
        seen.add(resolved)
    extras.sort(key=lambda item: item.relative_to(root).as_posix())
    return ordered + extras


def resolve_doc(doc_id: str, root: Path) -> Path:
    """把 id、别名或相对路径解析成文档根内的文件。"""
    query = _norm_query(doc_id)
    if not query:
        raise AgentDocsError("缺少文档 id。可用：" + _id_list())
    for topic in CATALOG:
        if query in _keys(topic):
            path = root / topic.path
            if not path.is_file():
                raise AgentDocsError(f"文档缺失：{topic.path}（id={topic.id}）")
            return path
    # 索引之外的相对路径（新增文件还没编进 CATALOG 时仍能打开）
    found = _safe_relative(root, doc_id)
    if found is not None:
        return found
    raise AgentDocsError(f"未知文档：{doc_id}\n可用：{_id_list()}")


def render_index(root: Path) -> str:
    """短索引：只告诉 Agent 该读哪一篇，不输出正文。"""
    width = max(len(topic.id) for topic in CATALOG)
    lines = [
        "Pilot Agent 文档（docs/to-agent）",
        "只打开当前任务的一篇：pilot docs show <id>",
        "检索：pilot docs search <关键词>",
        "细节以源码为准，勿通读全部。",
        "",
    ]
    missing: list[str] = []
    for topic in CATALOG:
        lines.append(f"{topic.id:<{width}}  {topic.when}")
        if not (root / topic.path).is_file():
            missing.append(topic.id)
    extras = [
        path.relative_to(root).as_posix()
        for path in iter_markdown(root)
        if path.relative_to(root).as_posix() not in {topic.path for topic in CATALOG}
    ]
    if extras:
        lines.append("")
        lines.append("未编入索引（pilot docs show <路径>）：" + ", ".join(extras))
    if missing:
        lines.append("")
        lines.append("缺失：" + ", ".join(missing))
    return "\n".join(lines)


def render_list(root: Path) -> str:
    """id 与相对路径，供核对打包内容。"""
    rows: list[tuple[str, str]] = []
    known = {topic.path: topic.id for topic in CATALOG}
    for path in iter_markdown(root):
        rel = path.relative_to(root).as_posix()
        rows.append((known.get(rel, rel[:-3] if rel.endswith(".md") else rel), rel))
    if not rows:
        raise AgentDocsError(f"文档目录没有 markdown：{root}")
    width = max(len(left) for left, _ in rows)
    return "\n".join(f"{left:<{width}}  {right}" for left, right in rows)


def render_show(doc_id: str, root: Path) -> str:
    """一篇文档全文。首行标明来源，方便 Agent 知道读的是哪一篇。"""
    path = resolve_doc(doc_id, root)
    rel = path.relative_to(root).as_posix()
    body = path.read_text(encoding="utf-8")
    header = f"<!-- docs/to-agent/{rel} -->"
    if body.endswith("\n"):
        return f"{header}\n{body}"
    return f"{header}\n{body}\n"


def render_search(keyword: str, root: Path, limit: int = 30) -> tuple[str, int]:
    """在文档中做大小写不敏感的子串检索。

    返回 ``(文本, 退出码)``：命中为 0，没有命中为 1。
    非法关键词抛 :class:`AgentDocsError`（调用方当成用法错误）。
    """
    needle = keyword.strip()
    if not needle:
        raise AgentDocsError("关键词为空")
    if limit < 1:
        raise AgentDocsError("--limit 必须 >= 1")
    folded = needle.casefold()
    groups: list[tuple[str, str, list[tuple[int, str]], bool]] = []
    shown = 0
    truncated = False
    for path in iter_markdown(root):
        if shown >= limit:
            truncated = True
            break
        rel = path.relative_to(root).as_posix()
        doc_id = _id_for_path(rel)
        file_hits: list[tuple[int, str]] = []
        extra_in_file = False
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if folded not in line.casefold():
                continue
            room = limit - shown - len(file_hits)
            if room <= 0 or len(file_hits) >= _SEARCH_PER_FILE:
                extra_in_file = True
                truncated = True
                break
            file_hits.append((line_no, _clip(line)))
        if not file_hits:
            continue
        groups.append((doc_id, rel, file_hits, extra_in_file))
        shown += len(file_hits)
    if not groups:
        return f"未找到：{needle}", 1
    lines: list[str] = []
    for doc_id, rel, hits, extra in groups:
        lines.append(f"[{doc_id}] {rel}")
        for line_no, line in hits:
            lines.append(f"  {line_no}: {line}")
        if extra:
            lines.append(f"  … 本篇还有命中，pilot docs show {doc_id}")
    if truncated:
        lines.append(f"（已截断，共展示 {shown} 条；缩小关键词或提高 --limit）")
    return "\n".join(lines), 0


def _id_for_path(rel: str) -> str:
    for topic in CATALOG:
        if topic.path == rel:
            return topic.id
    if rel.endswith(".md"):
        return rel[:-3]
    return rel


def _id_list() -> str:
    return " ".join(topic.id for topic in CATALOG)


def _keys(topic: DocTopic) -> set[str]:
    raw = {topic.id, topic.path, *topic.aliases}
    if topic.path.endswith(".md"):
        raw.add(topic.path[: -len(".md")])
    return {_norm_query(item) for item in raw}


def _norm_query(doc_id: str) -> str:
    text = doc_id.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.lower().endswith(".md"):
        text = text[: -len(".md")]
    return text.casefold()


def _safe_relative(root: Path, doc_id: str) -> Path | None:
    """只允许文档根内部的相对路径，拒绝绝对路径和 ``..`` 逃逸。"""
    raw = doc_id.strip().replace("\\", "/")
    if not raw or raw.startswith("/") or Path(doc_id.strip()).is_absolute():
        return None
    # ``..`` 即使 resolve 后仍在根内也不接受：Agent 不需要绕路
    if any(part == ".." for part in Path(raw).parts):
        return None
    candidate = (root / raw).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        return None
    if candidate.is_file() and candidate.suffix.lower() == ".md":
        return candidate
    return None


def _clip(line: str) -> str:
    text = " ".join(line.strip().split())
    if len(text) <= _LINE_WIDTH:
        return text
    return text[: _LINE_WIDTH - 1] + "…"
