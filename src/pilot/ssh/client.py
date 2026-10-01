"""Paramiko 驱动的用例层 SSH 客户端。"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pilot.core.config import SshSettings
from pilot.core.logging import get_logger

logger = get_logger("pilot.ssh")


def _require_paramiko():
    try:
        import paramiko
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "paramiko is required for Pilot SSH support. "
            "Reinstall with: pip install -e ."
        ) from exc
    return paramiko


@dataclass(frozen=True)
class SshResult:
    """远程命令执行结果。"""

    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def check(self) -> SshResult:
        """非 0 退出码时抛 RuntimeError。"""
        if not self.ok:
            detail = (self.stderr or self.stdout).strip() or "no output"
            raise RuntimeError(
                f"SSH command failed (exit={self.exit_code}): {self.command!r}\n{detail}"
            )
        return self


class SshClient:
    """用例侧 SSH：run / sudo / run_script / SFTP put/get。

    连接懒打开；优先用 fixture ``ssh`` / :func:`~pilot.ssh.session.get_ssh`。
    """

    def __init__(self, config: SshSettings) -> None:
        self.config = config
        self._client: Any | None = None

    @property
    def host(self) -> str:
        if not self.config.host:
            raise RuntimeError(
                "SSH host is not set; configure ``ssh.host`` in env YAML "
                "(or rely on db/base_url host fallback at load time)"
            )
        return self.config.host

    def connect(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.config.configured:
            raise RuntimeError(
                "SSH is not configured; add ``ssh.user`` (and usually host/password) "
                "to env YAML"
            )
        paramiko = _require_paramiko()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.config.port,
            username=self.config.user,
            password=self.config.password or None,
            key_filename=self.config.key_filename or None,
            timeout=self.config.connect_timeout,
            allow_agent=False,
            look_for_keys=bool(self.config.key_filename),
        )
        self._client = client
        logger.info(
            "ssh connected %s@%s:%s",
            self.config.user,
            self.host,
            self.config.port,
        )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None
                logger.info("ssh closed")

    def __enter__(self) -> SshClient:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def run(
        self,
        command: str,
        *,
        check: bool = False,
        get_pty: bool = False,
        timeout: float | None = None,
    ) -> SshResult:
        """执行远程 shell 命令。"""
        client = self.connect()
        cmd_timeout = self.config.command_timeout if timeout is None else timeout
        logger.debug("ssh run %s", command)
        stdin, stdout, stderr = client.exec_command(
            command, get_pty=get_pty, timeout=cmd_timeout
        )
        stdin.close()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = int(stdout.channel.recv_exit_status())
        result = SshResult(
            command=command, exit_code=exit_code, stdout=out, stderr=err
        )
        if check:
            result.check()
        return result

    def run_script(
        self,
        script: str,
        *,
        check: bool = True,
        interpreter: str = "bash -s",
        get_pty: bool = True,
        timeout: float | None = None,
    ) -> SshResult:
        """将多行脚本经 stdin 交给远程解释器（默认 bash -s）。"""
        client = self.connect()
        cmd_timeout = self.config.command_timeout if timeout is None else timeout
        logger.debug("ssh run_script via %s (%s bytes)", interpreter, len(script))
        stdin, stdout, stderr = client.exec_command(
            interpreter, get_pty=get_pty, timeout=cmd_timeout
        )
        stdin.write(script if script.endswith("\n") else script + "\n")
        stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = int(stdout.channel.recv_exit_status())
        result = SshResult(
            command=interpreter, exit_code=exit_code, stdout=out, stderr=err
        )
        if check:
            result.check()
        return result

    def sudo(
        self,
        command: str,
        *,
        check: bool = True,
        password: str | None = None,
        timeout: float | None = None,
    ) -> SshResult:
        """以 sudo 执行命令（有密码走 sudo -S，否则 sudo -n）。"""
        pw = self.config.password if password is None else password
        if pw:
            remote = (
                f"echo {shlex.quote(pw)} | sudo -S -p '' "
                f"bash -lc {shlex.quote(command)}"
            )
        else:
            remote = f"sudo -n bash -lc {shlex.quote(command)}"
        return self.run(remote, check=check, get_pty=True, timeout=timeout)

    def put(self, local: str | Path, remote: str) -> None:
        """本地文件上传到远程路径。"""
        client = self.connect()
        local_path = Path(local)
        with client.open_sftp() as sftp:
            sftp.put(str(local_path), remote)
        logger.debug("ssh put %s -> %s", local_path, remote)

    def get(self, remote: str, local: str | Path) -> None:
        """远程文件下载到本地路径。"""
        client = self.connect()
        local_path = Path(local)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with client.open_sftp() as sftp:
            sftp.get(remote, str(local_path))
        logger.debug("ssh get %s -> %s", remote, local_path)
