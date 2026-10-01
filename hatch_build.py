"""把 ``docs/to-agent`` 打进安装包。

``pilot docs`` 读取 ``pilot/templates/to-agent``（构建时从 docs 拷入）。

跳过规则与 ``pilot.scaffold.SKIP_DIR_NAMES`` 保持一致。
构建期不能依赖已安装的 pilot，所以跳过名单在这里再写一份。
"""

from __future__ import annotations

from pathlib import Path

# 与 pilot.scaffold.SKIP_DIR_NAMES 同步
_SKIP_DIR_NAMES = frozenset(
    {
        ".pytest_cache",
        "__pycache__",
        "reports",
        ".ruff_cache",
        ".mypy_cache",
        ".venv",
    }
)
_SKIP_SUFFIXES = {".pyc", ".pyo"}


def _add_tree(force: dict[str, str], src_dir: Path, src_prefix: str, dest_prefix: str) -> None:
    """把目录里的文件映射进 force_include。键是仓库相对路径，值是包内路径。"""
    for path in src_dir.rglob("*"):
        rel = path.relative_to(src_dir)
        if any(part in _SKIP_DIR_NAMES for part in rel.parts):
            continue
        if not path.is_file() or path.suffix in _SKIP_SUFFIXES:
            continue
        rel_posix = rel.as_posix()
        force[f"{src_prefix}/{rel_posix}"] = f"{dest_prefix}/{rel_posix}"


def collect_force_include(root: Path) -> dict[str, str]:
    """wheel 额外文件：Agent 文档。"""
    force: dict[str, str] = {}
    _include_first(
        force,
        (
            (root / "docs" / "to-agent", "docs/to-agent", root / "docs" / "to-agent" / "README.md"),
            (
                root / "pilot" / "templates" / "to-agent",
                "pilot/templates/to-agent",
                root / "pilot" / "templates" / "to-agent" / "README.md",
            ),
        ),
        "pilot/templates/to-agent",
    )
    return force


def _include_first(
    force: dict[str, str],
    candidates: tuple[tuple[Path, str, Path], ...],
    dest_prefix: str,
) -> None:
    """按顺序用第一个合格目录。源码树优先，避免和已展开的 templates 打两份。"""
    for src_dir, src_prefix, marker in candidates:
        if marker.is_file():
            _add_tree(force, src_dir, src_prefix, dest_prefix)
            return


try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:  # 单测只调用 collect_force_include，不要求装 hatchling
    BuildHookInterface = object  # type: ignore[misc,assignment]


class CustomBuildHook(BuildHookInterface):
    """构建时把过滤后的 Agent 文档强制包含进发行包。"""

    def initialize(self, version: str, build_data: dict) -> None:
        force: dict[str, str] = build_data.setdefault("force_include", {})
        force.update(collect_force_include(Path(self.root)))
