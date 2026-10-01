"""开测前由 AuthProvider 提供版本字段，写入 HTML 报告 Environment。"""

from __future__ import annotations

from typing import Any

from pilot.account.auth import get_auth_provider
from pilot.core.logging import get_logger

logger = get_logger("pilot.report.version")


def fill_report_version(metadata: dict[str, Any], pytestconfig: Any) -> None:
    """有 HTML 报告时，向 ``metadata`` 合并 ``AuthProvider.report_version_fields``。

    失败只记日志，不阻断用例。未配 HTML 路径或 Provider 返回空则跳过。
    """
    htmlpath = getattr(getattr(pytestconfig, "option", None), "htmlpath", None)
    if not htmlpath:
        return

    # 延迟导入，避免报告模块和 pytest 插件互相在加载期引用
    from pilot.pytest_plugin import _load_pilot_config

    try:
        cfg = _load_pilot_config(pytestconfig)
    except Exception as exc:
        logger.warning("skip system version; config load failed: %s", exc)
        return

    provider = get_auth_provider(pytestconfig)
    try:
        fields = provider.report_version_fields(cfg)
    except Exception as exc:
        logger.warning("report version fields failed: %s", exc)
        return

    if not fields:
        return

    metadata.update(fields)
    logger.info("system version fields=%s", fields)
