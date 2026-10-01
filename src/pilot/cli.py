"""Pilot 独立命令行：创建产品用例仓库、查询 Agent 文档。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pilot.agent_docs import (
    AgentDocsError,
    find_agent_docs,
    render_index,
    render_list,
    render_search,
    render_show,
)
from pilot.scaffold import ScaffoldError, create_case_repo


def build_parser() -> argparse.ArgumentParser:
    """构建 ``pilot`` 子命令解析器。"""
    parser = argparse.ArgumentParser(
        prog="pilot",
        description="Pilot 框架命令行",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser(
        "init",
        help="按框架约定生成产品用例仓库骨架",
    )
    init_parser.add_argument("dest", type=Path, help="新仓库目录（不存在则创建）")
    init_parser.add_argument(
        "--product",
        default=None,
        help="写入 config/product.yaml 的 product 字段；省略则用目标目录名",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="目标目录非空时仍写入，并覆盖同名文件（不删除多余文件）",
    )

    docs_parser = sub.add_parser(
        "docs",
        help="查询 Agent 文档（docs/to-agent）",
        description="给 Agent 按任务取文档：先看索引，再 show 一篇。安装包内已含这些文档。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  pilot docs\n"
            "  pilot docs show page\n"
            "  pilot docs show config\n"
            "  pilot docs search wait_ready"
        ),
    )
    docs_sub = docs_parser.add_subparsers(dest="docs_command")
    docs_sub.add_parser("list", help="列出文档 id 与相对路径")
    show_parser = docs_sub.add_parser("show", help="打印一篇文档全文")
    show_parser.add_argument(
        "doc_id",
        help="文档 id（readme/page/action/check/case/config/api/optional）或相对路径",
    )
    search_parser = docs_sub.add_parser("search", help="在文档中检索关键词")
    search_parser.add_argument("keyword", help="子串，大小写不敏感")
    search_parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="最多返回多少条命中（默认 30，单篇最多 5 条）",
    )
    return parser


def _prefer_utf8_stdio() -> None:
    """尽量用 UTF-8 写中文帮助。

    Windows 上 Python 默认按系统 ANSI 代码页编码 stdout，Cursor / 新终端实际是 UTF-8，
    不重配的话 ``pilot init --help`` 会乱码。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            continue


def _emit(text: str) -> None:
    """写到 stdout，并保证以换行结束（正文末尾已有换行时不重复空行）。"""
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def _cmd_init(args: argparse.Namespace) -> int:
    """按框架约定生成产品用例仓库骨架。"""
    written = create_case_repo(
        args.dest,
        product=args.product,
        force=args.force,
    )
    print(f"已创建用例仓库：{args.dest.resolve()}（{len(written)} 个文件）")
    return 0


def _cmd_docs(args: argparse.Namespace) -> int:
    """索引 / 单篇 / 检索。找不到文档或 id 非法时抛 AgentDocsError。"""
    root = find_agent_docs()
    command = args.docs_command
    if command is None:
        _emit(render_index(root))
        return 0
    if command == "list":
        _emit(render_list(root))
        return 0
    if command == "show":
        _emit(render_show(args.doc_id, root))
        return 0
    if command == "search":
        text, code = render_search(args.keyword, root, args.limit)
        _emit(text)
        return code
    raise AgentDocsError(f"unknown docs command: {command}")


def main(argv: list[str] | None = None) -> int:
    """命令入口。成功返回 0，检索无命中返回 1，用法或创建失败返回 2。"""
    _prefer_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "docs":
            return _cmd_docs(args)
    except ScaffoldError as exc:
        print(f"pilot init: {exc}", file=sys.stderr)
        return 2
    except AgentDocsError as exc:
        print(f"pilot docs: {exc}", file=sys.stderr)
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
