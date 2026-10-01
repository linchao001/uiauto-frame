"""wait_until 与 DbClient.wait_* 轮询。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pilot.core.config import DbSettings
from pilot.db.client import DbClient
from pilot.db.wait import PollResult, wait_until


def test_wait_until_succeeds() -> None:
    state = {"n": 0}

    def ready() -> bool:
        state["n"] += 1
        return state["n"] >= 2

    result = wait_until("ready", ready, timeout_sec=1.0, interval_sec=0.01)
    assert isinstance(result, PollResult)
    assert result.attempts >= 2
    assert result.label == "ready"


def test_wait_until_timeout_raises() -> None:
    with pytest.raises(AssertionError, match="timed out"):
        wait_until("never", lambda: False, timeout_sec=0.05, interval_sec=0.01)


def test_wait_present_and_field() -> None:
    """wait_present / wait_field：行出现与字段到位。"""
    cfg = DbSettings(user="root", database="app", password="x")
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    conn.ping = MagicMock()
    # select_one 连续调用：先空后有行；再字段到位
    cur.fetchall.side_effect = [
        [],
        [{"id": 1, "status": 1}],
        [{"id": 1, "status": 1}],
        [{"id": 1, "status": 3}],
    ]

    with patch("pymysql.connect", return_value=conn):
        db = DbClient(cfg)
        db.wait_present("orders", where={"id": 1}, timeout_sec=1.0, interval_sec=0.01)
        db.wait_field(
            "orders",
            "status",
            3,
            where={"id": 1},
            timeout_sec=1.0,
            interval_sec=0.01,
        )


def test_wait_absent_and_count() -> None:
    cfg = DbSettings(user="root", database="app", password="x")
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    conn.ping = MagicMock()
    cur.fetchall.side_effect = [
        [{"id": 1}],
        [],
    ]
    cur.fetchone.side_effect = [{"cnt": 0}, {"cnt": 2}, {"cnt": 2}]

    with patch("pymysql.connect", return_value=conn):
        db = DbClient(cfg)
        db.wait_absent("orders", where={"id": 1}, timeout_sec=1.0, interval_sec=0.01)
        db.wait_count(
            "orders", 2, where={"sku": "A"}, timeout_sec=1.0, interval_sec=0.01
        )
