"""pilot.core.http：轻量 JSON POST（供接口登录后注入会话）。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from pilot.core.http import HttpError, post_json


class _Handler(BaseHTTPRequestHandler):
    """测试用：回显 JSON body 与自定义请求头。"""

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        del format, args

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8") or "{}")
        client = self.headers.get("X-Client", "")
        # 中性假响应：仅验证 post_json 透传 body / headers，不模仿任何产品协议
        out = {
            "ok": True,
            "echo": {
                "user": payload.get("user"),
                "client": client,
                "token": "tok-1",
            },
        }
        body = json.dumps(out).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def http_server():
    """启动本机临时 HTTP 服务。"""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()


def test_post_json_returns_body(http_server: str) -> None:
    result = post_json(
        f"{http_server}/echo",
        {"user": "u", "password": "p"},
        headers={"X-Client": "test"},
    )
    assert result["ok"] is True
    assert result["echo"]["token"] == "tok-1"
    assert result["echo"]["client"] == "test"
    assert result["echo"]["user"] == "u"


def test_post_json_http_error() -> None:
    class _Err(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            del format, args

        def do_POST(self) -> None:  # noqa: N802
            body = b"boom"
            self.send_response(500)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), _Err)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        with pytest.raises(HttpError, match="500"):
            post_json(f"http://{host}:{port}/x", {})
    finally:
        server.shutdown()
