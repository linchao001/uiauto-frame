"""pilot 日志：格式、命名空间、helper 行号归因。"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path

from pilot.core.logging import LOG_FORMAT, PilotLogger, get_logger, register_log_origin_skip


def test_log_format_includes_lineno() -> None:
    assert "%(lineno)d" in LOG_FORMAT
    assert "%(asctime)s" in LOG_FORMAT
    assert "%(name)s" in LOG_FORMAT


def test_get_logger_prefixes_pilot() -> None:
    logger = get_logger("demo.ui")
    assert logger.name == "pilot.demo.ui"
    assert isinstance(logger, PilotLogger)


def test_get_logger_keeps_pilot_prefix() -> None:
    logger = get_logger("pilot.db")
    assert logger.name == "pilot.db"


def test_origin_skip_attributes_lineno_to_caller(tmp_path: Path) -> None:
    """helper 包一层 logger.info 时，lineno 应指向业务调用处。"""
    proxy = tmp_path / "case_log_proxy.py"
    proxy.write_text(
        "from pilot.core.logging import get_logger, register_log_origin_skip\n"
        "register_log_origin_skip(__file__)\n"
        "\n"
        "def emit(msg: str) -> None:\n"
        "    get_logger('test.origin_skip').info(msg)\n",
        encoding="utf-8",
    )

    spec = importlib.util.spec_from_file_location("case_log_proxy", proxy)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    root = logging.getLogger("pilot")
    handler = ListHandler()
    root.addHandler(handler)
    try:
        mod.emit("hello")
        expected_lineno = inspect.currentframe().f_lineno - 1  # type: ignore[union-attr]
    finally:
        root.removeHandler(handler)

    assert records, "expected a log record"
    rec = records[-1]
    assert isinstance(logging.getLogger("pilot.test.origin_skip"), PilotLogger)
    assert rec.getMessage() == "hello"
    assert rec.lineno == expected_lineno
    assert Path(rec.pathname).resolve() == Path(__file__).resolve()
    assert any(
        Path(p).name == "case_log_proxy.py"
        for p in __import__("pilot.core.logging", fromlist=["_ORIGIN_SKIP"])._ORIGIN_SKIP
    )


def test_step_logger_emits_one_line_success() -> None:
    """成功时只打一行 ✓，并写入报告步骤。"""
    from pilot.core.logging import StepLogger
    from pilot.report import capture
    from pilot.report.html_utils import pop_steps

    records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    class _Item:
        pass

    root = logging.getLogger("pilot")
    handler = ListHandler()
    root.addHandler(handler)
    item = _Item()
    token = capture.bind_test_item(item)
    try:
        with StepLogger().step("login"):
            pass
    finally:
        capture.reset_test_item(token)
        root.removeHandler(handler)

    messages = [r.getMessage() for r in records]
    step_msgs = [m for m in messages if "login" in m]
    assert len(step_msgs) == 1
    assert step_msgs[0] == "✓ login"
    assert "→" not in step_msgs[0]
    assert pop_steps(item) == [("login", "ok", "")]


def test_step_logger_report_false_skips_html() -> None:
    """report=False 时仅日志、不写入报告步骤。"""
    from pilot.core.logging import StepLogger
    from pilot.report import capture
    from pilot.report.html_utils import pop_steps

    records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    class _Item:
        pass

    root = logging.getLogger("pilot")
    handler = ListHandler()
    root.addHandler(handler)
    item = _Item()
    token = capture.bind_test_item(item)
    try:
        with StepLogger().step("open_profile_dialog", report=False):
            pass
    finally:
        capture.reset_test_item(token)
        root.removeHandler(handler)

    messages = [r.getMessage() for r in records]
    assert "✓ open_profile_dialog" in messages
    assert pop_steps(item) == []


def test_step_logger_emits_one_line_failure() -> None:
    """失败时只打一行带 <<< FAIL >>> 的 ✗，并写入报告失败步骤。"""
    from pilot.core.logging import StepLogger
    from pilot.report import capture
    from pilot.report.html_utils import pop_steps

    records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    class _Item:
        pass

    root = logging.getLogger("pilot")
    handler = ListHandler()
    root.addHandler(handler)
    item = _Item()
    token = capture.bind_test_item(item)
    try:
        try:
            with StepLogger().step("boom"):
                raise AssertionError("detail")
        except AssertionError as exc:
            assert str(exc).startswith("步骤失败: boom")
            assert "detail" in str(exc)
    finally:
        capture.reset_test_item(token)
        root.removeHandler(handler)

    messages = [r.getMessage() for r in records]
    step_msgs = [m for m in messages if "boom" in m or "期望" in m or "detail" in m]
    fail_msgs = [m for m in messages if "<<< FAIL >>>" in m]
    assert fail_msgs == ["✗ <<< FAIL >>> boom"]
    assert any("期望" in m or "detail" in m for m in messages)
    assert pop_steps(item) == [("boom", "fail", "detail")]


def test_step_logger_report_false_failure_keeps_plain_mark() -> None:
    """report=False 失败时仍单行 ✗，不改写异常、不进报告。"""
    from pilot.core.logging import StepLogger
    from pilot.report import capture
    from pilot.report.html_utils import pop_steps

    records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    class _Item:
        pass

    root = logging.getLogger("pilot")
    handler = ListHandler()
    root.addHandler(handler)
    item = _Item()
    token = capture.bind_test_item(item)
    try:
        try:
            with StepLogger().step("inner", report=False):
                raise AssertionError("x")
        except AssertionError as exc:
            assert str(exc) == "x"
    finally:
        capture.reset_test_item(token)
        root.removeHandler(handler)

    messages = [r.getMessage() for r in records]
    step_msgs = [m for m in messages if "inner" in m]
    assert step_msgs == ["✗ inner"]
    assert pop_steps(item) == []
