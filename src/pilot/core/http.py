"""轻量 HTTP JSON 客户端（无第三方依赖；供接口登录等场景）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class HttpError(RuntimeError):
    """HTTP 非 2xx 或响应非 JSON。"""

    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def post_json(
    url: str,
    body: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> Any:
    """POST JSON，返回已解析的响应体（通常为 dict）。

    Raises:
        HttpError: 状态码 >= 400，或响应体不是合法 JSON。
    """
    payload = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
    req_headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
    }
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(
        url,
        data=payload,
        headers=req_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", None) or resp.getcode()
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise HttpError(
            f"HTTP {exc.code} for POST {url}: {err_body[:500]}",
            status=exc.code,
            body=err_body,
        ) from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"POST {url} failed: {exc}") from exc
    except OSError as exc:
        # Windows 上错误响应对端提前断开时可能落到此处
        raise HttpError(f"POST {url} failed: {exc}") from exc

    if status is not None and int(status) >= 400:
        raise HttpError(
            f"HTTP {status} for POST {url}: {raw[:500]}",
            status=int(status),
            body=raw,
        )
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise HttpError(
            f"POST {url} returned non-JSON body: {raw[:500]}",
            status=int(status) if status is not None else None,
            body=raw,
        ) from exc
