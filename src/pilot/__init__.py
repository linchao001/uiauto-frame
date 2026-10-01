"""Pilot: product-agnostic Web UI automation framework."""

from pilot.cases import Case, cases, load_cases
from pilot.core.base_check import BaseCheck
from pilot.core.base_page import BasePage
from pilot.core.config import (
    DbSettings,
    FeishuSettings,
    PilotConfig,
    SshSettings,
    discover_envs,
    load_config,
    resolve_env_name,
)
from pilot.flow.base import BaseFlow
from pilot.report.html_utils import step

__all__ = [
    "BaseCheck",
    "BasePage",
    "BaseFlow",
    "Case",
    "DbSettings",
    "FeishuSettings",
    "PilotConfig",
    "SshSettings",
    "cases",
    "discover_envs",
    "load_cases",
    "load_config",
    "resolve_env_name",
    "step",
    "__version__",
]
__version__ = "0.1.0"
