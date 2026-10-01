"""Session 级 SshClient 绑定。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pilot.ssh.client import SshClient

_client: SshClient | None = None


def bind_ssh(client: SshClient | None) -> None:
    """绑定 session 级客户端供 :func:`get_ssh` 使用。"""
    global _client
    _client = client


def clear_ssh() -> None:
    """关闭并清空绑定。"""
    global _client
    if _client is not None:
        _client.close()
    _client = None


def get_ssh() -> SshClient:
    """返回已绑定的 :class:`~pilot.ssh.client.SshClient`。"""
    if _client is None:
        raise RuntimeError(
            "SSH is not bound; configure ``ssh`` in env YAML and run under the "
            "pilot pytest plugin, or call bind_ssh() first"
        )
    return _client
