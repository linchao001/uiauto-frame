"""SSH client（mock paramiko）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pilot.core.config import SshSettings
from pilot.ssh import session as ssh_session
from pilot.ssh.client import SshClient, SshResult
from pilot.ssh.session import bind_ssh, clear_ssh, get_ssh


@pytest.fixture
def ssh_config() -> SshSettings:
    return SshSettings(
        host="10.0.0.1",
        user="sshuser",
        password="sshuser",
    )


def test_ssh_result_check() -> None:
    ok = SshResult(command="true", exit_code=0, stdout="", stderr="")
    assert ok.check() is ok
    bad = SshResult(command="false", exit_code=1, stdout="", stderr="boom")
    with pytest.raises(RuntimeError, match="exit=1"):
        bad.check()


def test_run_command(ssh_config: SshSettings) -> None:
    stdout = MagicMock()
    stdout.read.return_value = b"hello\n"
    stdout.channel.recv_exit_status.return_value = 0
    stderr = MagicMock()
    stderr.read.return_value = b""
    stdin = MagicMock()

    raw = MagicMock()
    raw.exec_command.return_value = (stdin, stdout, stderr)

    with patch("pilot.ssh.client._require_paramiko") as require:
        paramiko = MagicMock()
        paramiko.SSHClient.return_value = raw
        paramiko.AutoAddPolicy.return_value = object()
        require.return_value = paramiko

        client = SshClient(ssh_config)
        result = client.run("uname -a", check=True)

    assert result.ok
    assert result.stdout == "hello\n"
    raw.connect.assert_called_once()
    assert raw.connect.call_args.kwargs["hostname"] == "10.0.0.1"
    assert raw.connect.call_args.kwargs["username"] == "sshuser"


def test_sudo_wraps_command(ssh_config: SshSettings) -> None:
    client = SshClient(ssh_config)
    with patch.object(client, "run") as run:
        run.return_value = SshResult("x", 0, "", "")
        client.sudo("systemctl restart nginx")
    cmd = run.call_args[0][0]
    assert "sudo -S" in cmd
    assert "systemctl restart nginx" in cmd


def test_run_script(ssh_config: SshSettings) -> None:
    stdout = MagicMock()
    stdout.read.return_value = b"ok\n"
    stdout.channel.recv_exit_status.return_value = 0
    stderr = MagicMock()
    stderr.read.return_value = b""
    stdin = MagicMock()
    raw = MagicMock()
    raw.exec_command.return_value = (stdin, stdout, stderr)

    with patch("pilot.ssh.client._require_paramiko") as require:
        paramiko = MagicMock()
        paramiko.SSHClient.return_value = raw
        paramiko.AutoAddPolicy.return_value = object()
        require.return_value = paramiko

        client = SshClient(ssh_config)
        result = client.run_script("echo hi", check=True)

    assert result.ok
    stdin.write.assert_called()
    stdin.channel.shutdown_write.assert_called_once()


def test_bind_and_get_ssh(ssh_config: SshSettings) -> None:
    prev = ssh_session._client
    clear_ssh()
    try:
        client = SshClient(ssh_config)
        bind_ssh(client)
        assert get_ssh() is client
    finally:
        clear_ssh()
        ssh_session._client = prev


def test_get_ssh_unbound_raises() -> None:
    prev = ssh_session._client
    clear_ssh()
    try:
        with pytest.raises(RuntimeError, match="not bound"):
            get_ssh()
    finally:
        ssh_session._client = prev
