"""Session 级 DbClient 绑定（fixture / get_db 共用）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pilot.db.client import DbClient

_client: DbClient | None = None


def bind_db(client: DbClient | None) -> None:
    """绑定 session 级客户端供 :func:`get_db` 使用。"""
    global _client
    _client = client


def clear_db() -> None:
    """关闭并清空绑定。"""
    global _client
    if _client is not None:
        _client.close()
    _client = None


def get_db() -> DbClient:
    """返回已绑定的 :class:`~pilot.db.client.DbClient`。

    需在 pytest 插件下配置 ``db``，或手动 :func:`bind_db`。
    """
    if _client is None:
        raise RuntimeError(
            "DB is not bound; configure ``db`` in env YAML and run under the "
            "pilot pytest plugin, or call bind_db() first"
        )
    return _client
