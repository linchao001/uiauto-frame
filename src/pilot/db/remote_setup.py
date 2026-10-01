"""经 SSH 开通 MariaDB 远程访问（实验室设备常只绑 127.0.0.1）。"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import TYPE_CHECKING

from pilot.core.logging import get_logger
from pilot.ssh.client import SshClient

if TYPE_CHECKING:
    from pilot.core.config import DbSettings, SshSettings

logger = get_logger("pilot.db.remote_setup")

# Debian/Ubuntu 系常见 MariaDB bind-address 配置文件
_BIND_CONF_FILES = (
    "/etc/mysql/mariadb.conf.d/99-custom.cnf",
    "/etc/mysql/mariadb.conf.d/50-server.cnf",
    "/etc/mysql/my.cnf",
)


def build_mariadb_remote_script(*, db_user: str, db_password: str, sudo_password: str) -> str:
    """生成开通 MariaDB 远程访问的 bash 脚本（bind + GRANT）。"""
    import shlex

    if sudo_password:
        sudo = f"echo {shlex.quote(sudo_password)} | sudo -S -p ''"
    else:
        sudo = "sudo -n"
    conf_list = " ".join(shlex.quote(p) for p in _BIND_CONF_FILES)
    sql_password = db_password.replace("\\", "\\\\").replace("'", "\\'")
    sql_user = db_user.replace("\\", "\\\\").replace("'", "\\'")
    mysql_pw = shlex.quote(db_password)
    return f"""set -e
echo '[1/5] set bind-address to 0.0.0.0 ...'
for f in {conf_list}; do
  if [ -f "$f" ]; then
    {sudo} sed -i 's/^[[:space:]]*bind-address[[:space:]]*=[[:space:]]*127\\.0\\.0\\.1/bind-address = 0.0.0.0/' "$f"
  fi
done

echo '[2/5] restart MariaDB ...'
{sudo} systemctl restart mariadb

echo '[3/5] wait for 3306 ...'
for i in 1 2 3 4 5 6 7 8 9 10; do
  if {sudo} ss -tulnp 2>/dev/null | grep -q 3306; then
    break
  fi
  sleep 1
done
{sudo} ss -tulnp | grep 3306 || true

echo '[4/5] grant remote access for {sql_user}@% ...'
mysql -u {shlex.quote(db_user)} -p{mysql_pw} -e "GRANT ALL PRIVILEGES ON *.* TO '{sql_user}'@'%' IDENTIFIED BY '{sql_password}' WITH GRANT OPTION; FLUSH PRIVILEGES;"

echo '[5/5] MariaDB remote setup done.'
"""


def setup_mariadb_remote(
    db: DbSettings,
    ssh: SshSettings | SshClient,
    *,
    settle_seconds: float = 2.0,
) -> None:
    """经框架 SSH 开通 MariaDB 远程连接：bind 0.0.0.0、重启、GRANT user@%。"""
    client = ssh if isinstance(ssh, SshClient) else SshClient(ssh)
    owns_client = not isinstance(ssh, SshClient)

    # ssh.host 为空时回落 db.host
    if not client.config.host and db.host:
        client.config = replace(client.config, host=db.host)

    if not client.config.configured:
        raise RuntimeError("SSH settings are not configured (ssh.user required)")

    script = build_mariadb_remote_script(
        db_user=db.user or "root",
        db_password=db.password,
        sudo_password=client.config.password,
    )

    logger.info(
        "SSH MariaDB remote setup %s@%s:%s",
        client.config.user,
        client.config.host or db.host,
        client.config.port,
    )
    try:
        result = client.run_script(script, check=False)
        if result.stdout.strip():
            logger.info("SSH setup stdout:\n%s", result.stdout.rstrip())
        if result.stderr.strip():
            logger.warning("SSH setup stderr:\n%s", result.stderr.rstrip())
        if not result.ok:
            detail = (result.stderr or result.stdout).strip() or "no output"
            raise RuntimeError(
                f"MariaDB remote setup via SSH failed (exit={result.exit_code}): {detail}"
            )
    finally:
        if owns_client:
            client.close()

    if settle_seconds > 0:
        time.sleep(settle_seconds)
    logger.info("MariaDB remote setup finished; retrying DB connect")
