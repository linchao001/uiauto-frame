"""报告里点击 Trace 时，通过自定义协议拉起 ``playwright show-trace``。

浏览器打不开本机程序。Windows 下注册 ``pilot-trace:``（当前用户，无需管理员），
链接形如 ``pilot-trace://show?path=<绝对路径>``。首次点击时浏览器会询问是否打开。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 注册表若按脚本路径回调，sys.path[0] 只是本文件目录，补上 src 才能 import pilot
if __name__ == "__main__" and __package__ in {None, ""}:
    _src = str(Path(__file__).resolve().parents[2])
    if _src not in sys.path:
        sys.path.insert(0, _src)

import subprocess
from urllib.parse import parse_qs, quote, urlparse

from pilot.core.logging import get_logger

logger = get_logger("pilot.report.trace")

SCHEME = "pilot-trace"
_registered = False


def trace_open_href(path: Path) -> str:
    """生成可放进 HTML 的协议链接。路径放在 query 里，避免盘符冒号被浏览器吃掉。"""
    resolved = str(Path(path).resolve())
    return f"{SCHEME}://show?path={quote(resolved, safe='')}"


def path_from_protocol_url(url: str) -> Path:
    """从协议回调参数解析 zip 绝对路径。"""
    raw = url.strip().strip('"').strip()
    parsed = urlparse(raw)
    if parsed.scheme.lower() != SCHEME:
        raise ValueError(f"not a {SCHEME} url: {raw}")
    values = parse_qs(parsed.query).get("path") or []
    if not values or not str(values[0]).strip():
        raise ValueError(f"missing path in {raw}")
    return Path(values[0])


def _handler_python() -> str:
    """协议回调用 pythonw，避免点击时闪一个控制台。"""
    exe = Path(sys.executable).resolve()
    if exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.is_file():
            return str(pythonw)
    return str(exe)


def _show_trace_python() -> str:
    """show-trace 仍用 python.exe；pythonw 下 Playwright CLI 可能没有标准输出句柄。"""
    exe = Path(sys.executable).resolve()
    if exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.is_file():
            return str(console)
    return str(exe)


def protocol_command() -> str:
    """注册表 command：用已安装的包拉起本模块，并把完整 URL 作为唯一参数。"""
    exe = _handler_python()
    return f'"{exe}" -m pilot.report.trace_protocol "%1"'


def ensure_trace_protocol() -> bool:
    """在当前用户注册 ``pilot-trace``。非 Windows 或写注册表失败则返回 False。"""
    global _registered
    if _registered:
        return True
    if sys.platform != "win32":
        return False
    import winreg

    command = protocol_command()
    base = rf"Software\Classes\{SCHEME}"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Pilot Trace Viewer")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
    except OSError as exc:
        logger.warning("could not register %s protocol: %s", SCHEME, exc)
        return False
    _registered = True
    logger.info("trace viewer protocol registered: %s", SCHEME)
    return True


def open_trace(path: Path) -> None:
    """拉起 Trace Viewer。只接受已存在的 .zip，且不经 shell。"""
    target = Path(path)
    if target.suffix.lower() != ".zip":
        raise SystemExit(f"refuse to open non-zip: {target}")
    if not target.is_file():
        raise SystemExit(f"trace not found: {target}")

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [_show_trace_python(), "-m", "playwright", "show-trace", str(target)],
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main(argv: list[str] | None = None) -> int:
    """协议回调入口。``argv[1]`` 为浏览器传来的完整 URL。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(f"usage: {SCHEME}://show?path=<trace.zip>", file=sys.stderr)
        return 2
    try:
        path = path_from_protocol_url(args[0])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    open_trace(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
