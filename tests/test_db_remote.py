"""DB SSH 远程开通与 connect 重试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pilot.core.config import DbSettings, SshSettings
from pilot.db.client import DbClient
from pilot.db.remote_setup import build_mariadb_remote_script, setup_mariadb_remote
from pilot.ssh.client import SshClient, SshResult


@pytest.fixture
def db_config() -> DbSettings:
    return DbSettings(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="secret",
        database="testdb",
        autocommit=True,
        auto_setup_remote=True,
    )


def test_build_mariadb_remote_script_contains_steps() -> None:
    script = build_mariadb_remote_script(
        db_user="root",
        db_password="db-pass",
        sudo_password="sshuser",
    )
    assert "bind-address = 0.0.0.0" in script
    assert "systemctl restart mariadb" in script
    assert "GRANT ALL PRIVILEGES" in script
    assert "root'@'%'" in script
    assert "db-pass" in script
    assert "sudo -S" in script


def test_setup_mariadb_remote_uses_ssh_client() -> None:
    cfg = DbSettings(
        host="10.0.0.1",
        user="root",
        password="db-pass",
        database="app",
    )
    ssh = SshClient(
        SshSettings(host="10.0.0.1", user="sshuser", password="sshuser")
    )
    result = SshResult(
        command="bash -s",
        exit_code=0,
        stdout="[5/5] done\n",
        stderr="",
    )
    with (
        patch.object(ssh, "run_script", return_value=result) as run_script,
        patch("pilot.db.remote_setup.time.sleep"),
    ):
        setup_mariadb_remote(cfg, ssh, settle_seconds=0)
    run_script.assert_called_once()
    script = run_script.call_args[0][0]
    assert "systemctl restart mariadb" in script


def test_connect_retries_after_ssh_remote_setup(db_config: DbSettings) -> None:
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    conn.ping = MagicMock()
    ssh = SshClient(SshSettings(host="127.0.0.1", user="sshuser", password="sshuser"))

    with (
        patch("pymysql.connect", side_effect=[OSError("refused"), conn]) as connect,
        patch("pilot.db.remote_setup.setup_mariadb_remote") as setup,
    ):
        db = DbClient(db_config, ssh=ssh)
        assert db.connect() is conn
    setup.assert_called_once()
    assert connect.call_count == 2
    assert db._remote_setup_done is True


def test_connect_skips_ssh_when_not_configured(db_config: DbSettings) -> None:
    with patch("pymysql.connect", side_effect=OSError("refused")):
        db = DbClient(db_config)
        with pytest.raises(OSError, match="refused"):
            db.connect()


def test_connect_skips_when_auto_setup_disabled(db_config: DbSettings) -> None:
    db_config.auto_setup_remote = False
    ssh = SshClient(SshSettings(host="127.0.0.1", user="sshuser", password="x"))
    with patch("pymysql.connect", side_effect=OSError("refused")):
        db = DbClient(db_config, ssh=ssh)
        with pytest.raises(OSError, match="refused"):
            db.connect()
