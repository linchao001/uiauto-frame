"""Pilot 结构化日志：格式、命名空间、helper 行号归因、pytest 集成。"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


_CONFIGURED = False

# 含行号，便于 helper 封装后仍能定位业务调用处
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s"

# 由 pytest 插件设置；勿用 ``"pytest" in sys.modules``（import 时可能误判）
_PYTEST_FLAG = "_pilot_pytest_logging"

# 归因时跳过的绝对路径（产品仓 helpers 等）
_ORIGIN_SKIP: set[str] = set()


def register_log_origin_skip(*paths: str | Path) -> None:
    """登记 helper 文件，使日志 filename/lineno 归因到业务调用处。"""
    for path in paths:
        _ORIGIN_SKIP.add(os.path.normcase(os.path.abspath(str(path))))


def enable_pytest_logging() -> None:
    """标记处于 pytest 环境（不向 stdout 挂 StreamHandler）。"""
    setattr(sys, _PYTEST_FLAG, True)


def _under_pytest() -> bool:
    return bool(getattr(sys, _PYTEST_FLAG, False))


def _is_stdout_stream_handler(handler: logging.Handler) -> bool:
    """是否为写向 stdout/stderr 的普通 StreamHandler（非 FileHandler）。"""
    if type(handler) is not logging.StreamHandler:
        return False
    stream = getattr(handler, "stream", None)
    return stream in (sys.stdout, sys.stderr, getattr(sys, "__stdout__", None))


def _strip_stdout_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if _is_stdout_stream_handler(handler):
            logger.removeHandler(handler)
            handler.close()


def _logging_srcfile() -> str | None:
    src = getattr(logging, "_srcfile", None)
    return os.path.normcase(src) if src else None


class PilotLogger(logging.Logger):
    """跳过已登记 helper / logging 内部帧，把调用点归因到业务代码。"""

    def findCaller(self, stack_info: bool = False, stacklevel: int = 1):
        f = logging.currentframe()
        if f is not None:
            f = f.f_back
        rv = "(unknown file)", 0, "(unknown function)", None
        srcfile = _logging_srcfile()
        while hasattr(f, "f_code"):
            co = f.f_code
            filename = os.path.normcase(co.co_filename)
            if filename == srcfile or filename in _ORIGIN_SKIP:
                f = f.f_back
                continue
            if stacklevel > 1:
                stacklevel -= 1
                f = f.f_back
                continue
            sinfo = None
            if stack_info:
                import io
                import traceback

                sio = io.StringIO()
                sio.write("Stack (most recent call last):\n")
                traceback.print_stack(f, file=sio)
                sinfo = sio.getvalue().rstrip("\n")
            rv = (co.co_filename, f.f_lineno, co.co_name, sinfo)
            break
        return rv


# 新创建的 pilot.* logger 使用 PilotLogger
if not issubclass(logging.getLoggerClass(), PilotLogger):
    logging.setLoggerClass(PilotLogger)


def configure_logging(level: int | str = logging.INFO) -> None:
    """配置 ``pilot`` 日志树。

    pytest 下不挂 stdout StreamHandler：实时输出走 pytest ``log_cli``，
    避免 Captured stdout 重复，以及 Windows cp936 中文乱码。
    """
    global _CONFIGURED
    root = logging.getLogger("pilot")
    root.setLevel(
        level if isinstance(level, int) else getattr(logging, str(level).upper(), logging.INFO)
    )
    root.propagate = False

    if _under_pytest():
        _strip_stdout_handlers(root)
        if not root.handlers:
            root.addHandler(logging.NullHandler())
        _CONFIGURED = True
        return

    if _CONFIGURED:
        return
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str = "pilot") -> logging.Logger:
    """取 / 创建 ``pilot.*`` logger；未带前缀时自动补上。"""
    if not name.startswith("pilot"):
        name = f"pilot.{name}"
    configure_logging()
    return logging.getLogger(name)


class StepLogger:
    """步骤轨迹：结束时单行打 ✓/✗；可选写入 HTML 报告。

    - ``report=True``（默认）：用例功能步骤 → 日志 + 报告
    - ``report=False``：Action 内部过程 → 仅日志
    """

    def __init__(self) -> None:
        self._logger = get_logger("pilot")

    @contextmanager
    def step(self, name: str, *, report: bool = True) -> Iterator[None]:
        # 延迟导入：避免 logging ↔ report 环依赖
        from pilot.report.html_utils import record_step

        try:
            yield
        except Exception as exc:
            if report:
                from pilot.core.assert_format import (
                    build_step_failure_message,
                    summarize_failure_message,
                )

                reason = summarize_failure_message(str(exc))
                # 用例步骤失败：醒目标记 + 原因，便于一眼看出「哪里 / 为什么」
                # 不打步骤序号：序号与报告步骤对不齐，容易误读
                self._logger.error("✗ <<< FAIL >>> %s", name)
                for line in reason.splitlines():
                    self._logger.error("    %s", line)
                record_step(name, "fail", reason)
                if isinstance(exc, AssertionError):
                    msg = str(exc)
                    if not msg.startswith("步骤失败:"):
                        raise AssertionError(
                            build_step_failure_message(name, exc)
                        ) from None
                raise
            # Action 内部失败：单行 ✗ 即可
            self._logger.error("✗ %s", name)
            raise
        else:
            self._logger.info("✓ %s", name)
            if report:
                record_step(name, "ok")
