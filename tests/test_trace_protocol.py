"""报告 Trace 链接与协议回调解析。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pilot.core.report_attach import _trace_link_html
from pilot.report.trace_protocol import (
    SCHEME,
    main,
    path_from_protocol_url,
    protocol_command,
    trace_open_href,
)


def test_trace_open_href_roundtrip(tmp_path: Path) -> None:
    zip_path = tmp_path / "dir a" / "trace.zip"
    zip_path.parent.mkdir()
    zip_path.write_bytes(b"zip")
    href = trace_open_href(zip_path)
    assert href.startswith(f"{SCHEME}://show?path=")
    assert path_from_protocol_url(href) == zip_path.resolve()
    assert path_from_protocol_url(f'"{href}"') == zip_path.resolve()


def test_path_from_protocol_url_rejects_other_scheme() -> None:
    with pytest.raises(ValueError, match="not a"):
        path_from_protocol_url("https://example.com/trace.zip")


def test_trace_link_html_uses_protocol(tmp_path: Path) -> None:
    zip_path = tmp_path / "trace.zip"
    zip_path.write_bytes(b"zip")
    html = _trace_link_html(zip_path)
    assert "打开 Trace" in html
    assert f'href="{SCHEME}://show?path=' in html
    assert "target=" not in html


def test_protocol_command_quotes_script() -> None:
    command = protocol_command()
    assert "-m pilot.report.trace_protocol" in command
    assert command.endswith('"%1"')


def test_main_opens_existing_zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    zip_path = tmp_path / "trace.zip"
    zip_path.write_bytes(b"zip")
    href = trace_open_href(zip_path)
    opened: list[Path] = []
    monkeypatch.setattr(
        "pilot.report.trace_protocol.open_trace",
        lambda path: opened.append(path),
    )
    assert main([href]) == 0
    assert opened == [zip_path.resolve()]


def test_main_rejects_missing_arg() -> None:
    assert main([]) == 2


def test_ensure_trace_protocol_writes_hkcu(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform != "win32":
        pytest.skip("windows protocol")
    import pilot.report.trace_protocol as mod

    monkeypatch.setattr(mod, "_registered", False)
    values: dict[tuple[str, str], str] = {}

    class _Key:
        def __init__(self, path: str) -> None:
            self.path = path

        def __enter__(self) -> _Key:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    def create_key(_root: object, path: str) -> _Key:
        return _Key(path)

    def set_value(key: _Key, name: str, _reserved: int, _typ: int, value: str) -> None:
        values[(key.path, name)] = value

    fake = MagicMock()
    fake.HKEY_CURRENT_USER = object()
    fake.REG_SZ = 1
    fake.CreateKey.side_effect = create_key
    fake.SetValueEx.side_effect = set_value
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert mod.ensure_trace_protocol() is True
    base = rf"Software\Classes\{SCHEME}"
    assert values[(base, "URL Protocol")] == ""
    assert "%1" in values[(base + r"\shell\open\command", "")]
