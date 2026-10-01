"""产品可实现的 pytest 钩子（不作为插件加载）。"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.hookspec
def pytest_pilot_report_metadata(metadata: dict[str, Any], config: Any) -> None:
    """HTML 报告 Environment 快照前追加字段。

    框架已清空默认项，并写入 ``base_url``（若有）；有 HTML 报告时还会合并
    ``AuthProvider.report_version_fields``（失败不阻断）。实现方只追加自己的键，
    不要 ``clear()``。钩子内失败应自行处理，避免阻断开测。
    """
