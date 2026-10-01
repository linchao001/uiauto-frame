"""PyMySQL 驱动的用例层 DB 客户端（表级 CRUD + raw SQL + wait_*）。"""

from __future__ import annotations

import re
from collections.abc import Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from pilot.core.config import DbSettings
from pilot.core.logging import get_logger
from pilot.db.wait import PollResult, wait_until

logger = get_logger("pilot.db")

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ORDER_BY_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\s+(ASC|DESC))?(\s*,\s*[A-Za-z_][A-Za-z0-9_]*(\s+(ASC|DESC))?)*$",
    re.IGNORECASE,
)

if TYPE_CHECKING:
    from pilot.core.config import SshSettings
    from pilot.ssh.client import SshClient


def _require_pymysql():
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "PyMySQL is required for Pilot DB support. "
            "Reinstall with: pip install -e ."
        ) from exc
    return pymysql, DictCursor


def quote_ident(name: str) -> str:
    """校验并反引号包裹表/列名，防注入。"""
    if not _IDENT_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f"`{name}`"


def _build_where(
    where: Mapping[str, Any] | None,
) -> tuple[str, list[Any]]:
    if not where:
        return "", []
    parts: list[str] = []
    args: list[Any] = []
    for key, value in where.items():
        col = quote_ident(key)
        if value is None:
            parts.append(f"{col} IS NULL")
        elif isinstance(value, (list, tuple, set)):
            values = list(value)
            if not values:
                parts.append("1=0")
            else:
                placeholders = ", ".join(["%s"] * len(values))
                parts.append(f"{col} IN ({placeholders})")
                args.extend(values)
        else:
            parts.append(f"{col} = %s")
            args.append(value)
    return " WHERE " + " AND ".join(parts), args


class DbClient:
    """用例侧 DB API：表级 CRUD + raw SQL + 异步 wait_*。

    连接 / 游标 / 提交 / ping 重连由本类处理；用例只调业务方法。

    当 ``auto_setup_remote`` 开启且注入了 session ``ssh`` 时，首次 TCP 失败会
    经 SSH 开通 MariaDB 远程访问后再重连一次。
    """

    def __init__(
        self,
        config: DbSettings,
        ssh: SshSettings | SshClient | None = None,
    ) -> None:
        self.config = config
        self.ssh = ssh
        self._conn: Any | None = None
        self._remote_setup_done = False

    @property
    def _ssh_ready(self) -> bool:
        if not self.config.auto_setup_remote or self.ssh is None:
            return False
        cfg = self.ssh.config if hasattr(self.ssh, "config") else self.ssh
        return bool(getattr(cfg, "configured", False))

    def _open_connection(self) -> Any:
        pymysql, DictCursor = _require_pymysql()
        kwargs: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "database": self.config.database,
            "charset": self.config.charset,
            "connect_timeout": self.config.connect_timeout,
            "autocommit": self.config.autocommit,
            "cursorclass": DictCursor,
        }
        if self.config.read_timeout is not None:
            kwargs["read_timeout"] = self.config.read_timeout
        if self.config.write_timeout is not None:
            kwargs["write_timeout"] = self.config.write_timeout
        self._conn = pymysql.connect(**kwargs)
        logger.info(
            "db connected %s@%s:%s/%s",
            self.config.user,
            self.config.host,
            self.config.port,
            self.config.database,
        )
        return self._conn

    def connect(self) -> Any:
        if self._conn is not None:
            return self._conn
        try:
            return self._open_connection()
        except Exception as exc:
            if not self._ssh_ready or self._remote_setup_done:
                raise
            logger.warning(
                "db connect failed (%s); attempting SSH MariaDB remote setup",
                exc,
            )
            from pilot.db.remote_setup import setup_mariadb_remote

            self._remote_setup_done = True
            try:
                assert self.ssh is not None
                setup_mariadb_remote(self.config, self.ssh)
            except Exception as setup_exc:
                raise RuntimeError(
                    f"DB connect failed ({exc}); MariaDB remote setup via SSH "
                    f"also failed: {setup_exc}"
                ) from setup_exc
            return self._open_connection()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
                logger.info("db closed")

    def __enter__(self) -> DbClient:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def ping(self, *, reconnect: bool = True) -> None:
        conn = self.connect()
        conn.ping(reconnect=reconnect)

    @contextmanager
    def cursor(self) -> Generator[Any, None, None]:
        self.ping(reconnect=True)
        assert self._conn is not None
        cur = self._conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()

    # ------------------------------------------------------------------ raw SQL
    def execute(self, sql: str, args: Sequence[Any] | Mapping[str, Any] | None = None) -> int:
        """执行写 / DDL；返回影响行数。"""
        with self.cursor() as cur:
            affected = cur.execute(sql, args)
            if not self.config.autocommit:
                self.commit()
            logger.debug("db execute affected=%s sql=%s", affected, sql)
            return int(affected or 0)

    def executemany(self, sql: str, args_seq: Iterable[Sequence[Any] | Mapping[str, Any]]) -> int:
        with self.cursor() as cur:
            affected = cur.executemany(sql, list(args_seq))
            if not self.config.autocommit:
                self.commit()
            return int(affected or 0)

    def fetch_one(
        self, sql: str, args: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self.cursor() as cur:
            cur.execute(sql, args)
            row = cur.fetchone()
            return dict(row) if row is not None else None

    def fetch_all(
        self, sql: str, args: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]

    def fetch_value(
        self, sql: str, args: Sequence[Any] | Mapping[str, Any] | None = None
    ) -> Any:
        """返回首行首列（或 None）。"""
        row = self.fetch_one(sql, args)
        if row is None:
            return None
        return next(iter(row.values()))

    # ------------------------------------------------------------------ table CRUD
    def insert(self, table: str, data: Mapping[str, Any]) -> int:
        """插入一行；返回 lastrowid（无则为 0）。"""
        if not data:
            raise ValueError("insert data must not be empty")
        cols = ", ".join(quote_ident(k) for k in data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO {quote_ident(table)} ({cols}) VALUES ({placeholders})"
        with self.cursor() as cur:
            cur.execute(sql, tuple(data.values()))
            last_id = int(cur.lastrowid or 0)
            if not self.config.autocommit:
                self.commit()
            logger.debug("db insert table=%s id=%s", table, last_id)
            return last_id

    def insert_many(self, table: str, rows: Sequence[Mapping[str, Any]]) -> int:
        """同列多行批量插入；返回影响行数。"""
        if not rows:
            return 0
        keys = list(rows[0].keys())
        if not keys:
            raise ValueError("insert_many rows must not be empty mappings")
        cols = ", ".join(quote_ident(k) for k in keys)
        placeholders = ", ".join(["%s"] * len(keys))
        sql = f"INSERT INTO {quote_ident(table)} ({cols}) VALUES ({placeholders})"
        args_seq = [tuple(row[k] for k in keys) for row in rows]
        return self.executemany(sql, args_seq)

    def select(
        self,
        table: str,
        *,
        fields: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        if fields:
            cols = ", ".join(quote_ident(f) for f in fields)
        else:
            cols = "*"
        sql = f"SELECT {cols} FROM {quote_ident(table)}"
        where_sql, args = _build_where(where)
        sql += where_sql
        if order_by:
            if not _ORDER_BY_RE.match(order_by.strip()):
                raise ValueError(f"Invalid order_by: {order_by!r}")
            sql += f" ORDER BY {order_by.strip()}"
        if limit is not None:
            sql += " LIMIT %s"
            args.append(int(limit))
            if offset is not None:
                sql += " OFFSET %s"
                args.append(int(offset))
        elif offset is not None:
            raise ValueError("offset requires limit")
        return self.fetch_all(sql, args)

    def select_one(
        self,
        table: str,
        *,
        fields: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(
            table, fields=fields, where=where, order_by=order_by, limit=1
        )
        return rows[0] if rows else None

    def count(self, table: str, *, where: Mapping[str, Any] | None = None) -> int:
        sql = f"SELECT COUNT(*) AS cnt FROM {quote_ident(table)}"
        where_sql, args = _build_where(where)
        sql += where_sql
        value = self.fetch_value(sql, args)
        return int(value or 0)

    def update(
        self,
        table: str,
        data: Mapping[str, Any],
        *,
        where: Mapping[str, Any] | None = None,
        force: bool = False,
    ) -> int:
        if not data:
            raise ValueError("update data must not be empty")
        if not where and not force:
            raise ValueError("update without where requires force=True")
        sets = ", ".join(f"{quote_ident(k)} = %s" for k in data.keys())
        sql = f"UPDATE {quote_ident(table)} SET {sets}"
        args: list[Any] = list(data.values())
        where_sql, where_args = _build_where(where)
        sql += where_sql
        args.extend(where_args)
        return self.execute(sql, args)

    def delete(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        force: bool = False,
    ) -> int:
        if not where and not force:
            raise ValueError("delete without where requires force=True")
        sql = f"DELETE FROM {quote_ident(table)}"
        where_sql, args = _build_where(where)
        sql += where_sql
        return self.execute(sql, args)

    # ------------------------------------------------------------------ async poll
    def wait_absent(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        timeout_sec: float = 30.0,
        interval_sec: float = 0.5,
        label: str | None = None,
    ) -> PollResult:
        """轮询直到无匹配行（异步删除 / 清场）。"""
        poll_label = label or f"{table} absent where={where!r}"
        row_holder: list[dict[str, Any] | None] = [None]

        def predicate() -> bool:
            row_holder[0] = self.select_one(table, where=where)
            return row_holder[0] is None

        return wait_until(
            poll_label,
            predicate,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            on_poll=lambda: row_holder[0],
        )

    def wait_present(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        timeout_sec: float = 30.0,
        interval_sec: float = 0.5,
        label: str | None = None,
    ) -> PollResult:
        """轮询直到出现匹配行。"""
        poll_label = label or f"{table} present where={where!r}"
        row_holder: list[dict[str, Any] | None] = [None]

        def predicate() -> bool:
            row_holder[0] = self.select_one(table, where=where, order_by=order_by)
            return row_holder[0] is not None

        return wait_until(
            poll_label,
            predicate,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            on_poll=lambda: row_holder[0],
        )

    def wait_count(
        self,
        table: str,
        expected: int,
        *,
        where: Mapping[str, Any] | None = None,
        timeout_sec: float = 30.0,
        interval_sec: float = 0.5,
        label: str | None = None,
    ) -> PollResult:
        """轮询直到 COUNT(*) == expected。"""
        poll_label = label or f"{table} count={expected} where={where!r}"
        count_holder: list[int] = [0]

        def predicate() -> bool:
            count_holder[0] = self.count(table, where=where)
            return count_holder[0] == expected

        return wait_until(
            poll_label,
            predicate,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            on_poll=lambda: count_holder[0],
        )

    def wait_field(
        self,
        table: str,
        field: str,
        expected: Any,
        *,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        timeout_sec: float = 30.0,
        interval_sec: float = 0.5,
        label: str | None = None,
    ) -> PollResult:
        """轮询直到行的 ``field`` 等于 expected（行缺失继续等）。"""
        poll_label = label or f"{table}.{field}={expected!r} where={where!r}"
        row_holder: list[dict[str, Any] | None] = [None]

        def predicate() -> bool:
            row_holder[0] = self.select_one(table, where=where, order_by=order_by)
            if row_holder[0] is None:
                return False
            return row_holder[0].get(field) == expected

        return wait_until(
            poll_label,
            predicate,
            timeout_sec=timeout_sec,
            interval_sec=interval_sec,
            on_poll=lambda: row_holder[0],
        )
