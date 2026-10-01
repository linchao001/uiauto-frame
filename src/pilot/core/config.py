"""Configuration loading for Pilot.

支持两种布局（可并存，优先分层）：

1. 分层::

       config/product.yaml
       config/env/<device>.yaml

2. 单文件兼容::

       config/env.yaml   # top-level ``default`` + 命名 env 块

设备凭据与真实业务接口路径应放在本地 ``env/*.yaml``（勿提交仓库）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

DEFAULT_ENV = "local"
_ENV_SUFFIXES = (".yaml", ".yml")


@dataclass
class BrowserSettings:
    browser: str = "chromium"
    channel: str | None = None  # e.g. "chrome" / "msedge" to use system browser
    headless: bool = True
    slow_mo: int = 0
    viewport_width: int = 1280
    viewport_height: int = 720
    timeout_ms: int = 15_000
    navigation_timeout_ms: int = 30_000
    action_retries: int = 2
    action_retry_delay_ms: int = 400
    trace: str = "retain-on-failure"  # on | off | retain-on-failure
    screenshot_on_failure: bool = True
    video: str = "off"  # on | off | retain-on-failure
    base_url: str = ""


@dataclass
class SshSettings:
    """SSH 连接：用例远程命令 / SFTP，以及 DB 自动开远程。

    默认空实例未启用；有 ``user`` 即 ``enabled``。
    """

    host: str = ""
    port: int = 22
    user: str = ""
    password: str = ""
    key_filename: str = ""
    connect_timeout: float = 10.0
    command_timeout: float = 120.0

    @property
    def enabled(self) -> bool:
        return bool(self.user)

    @property
    def configured(self) -> bool:
        """与 enabled 同义，供 DB remote-setup 判断。"""
        return self.enabled


@dataclass
class DbSettings:
    """单库 MySQL / MariaDB 连接（PyMySQL）。

    默认空实例表示未启用；``user`` 或 ``database`` 任一非空即 ``enabled``。
    """

    host: str = "127.0.0.1"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = ""
    charset: str = "utf8mb4"
    connect_timeout: float = 10.0
    read_timeout: float | None = None
    write_timeout: float | None = None
    autocommit: bool = True
    auto_setup_remote: bool = True

    @property
    def enabled(self) -> bool:
        return bool(self.database or self.user)


@dataclass
class FeishuSettings:
    """飞书群机器人 Webhook 通知（会话结束汇总）。

    YAML 的 ``enabled`` 映射到 ``switch``；对外 ``enabled`` 属性还要求 webhook 非空。
    """

    webhook: str = ""
    include_failures: bool = False
    failure_limit: int = 20
    timeout_sec: float = 5.0
    switch: bool = False  # YAML enabled；勿与属性 enabled 混淆

    def __init__(
        self,
        *,
        enabled: bool = False,
        webhook: str = "",
        include_failures: bool = False,
        failure_limit: int = 20,
        timeout_sec: float = 5.0,
    ) -> None:
        # 构造参数用 enabled，与 YAML / 调用方习惯一致
        self.switch = enabled
        self.webhook = webhook
        self.include_failures = include_failures
        self.failure_limit = failure_limit
        self.timeout_sec = timeout_sec

    @property
    def enabled(self) -> bool:
        """总开关为真且配置了 webhook 时才启用。"""
        return bool(self.switch and self.webhook)


@dataclass
class PilotConfig:
    env: str = DEFAULT_ENV
    browser: BrowserSettings = field(default_factory=BrowserSettings)
    db: DbSettings = field(default_factory=DbSettings)
    ssh: SshSettings = field(default_factory=SshSettings)
    feishu: FeishuSettings = field(default_factory=FeishuSettings)
    accounts: dict[str, dict[str, str]] = field(default_factory=dict)
    # UI 自动化默认登录角色；用例未指定账号时使用（产品自定 key）
    default_account: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        return self.browser.base_url


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 映射；文件不存在返回空 dict。"""
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must be a mapping: {path}")
    return raw


def discover_envs(config_dir: str | Path) -> list[str]:
    """返回 ``config_dir/env/*.y{a}ml`` 下已发现的设备/环境名（排序）。"""
    env_dir = Path(config_dir) / "env"
    if not env_dir.is_dir():
        return []
    names: set[str] = set()
    for path in env_dir.iterdir():
        if path.is_file() and path.suffix.lower() in _ENV_SUFFIXES:
            names.add(path.stem)
    return sorted(names)


def _env_file(root: Path, env_name: str) -> Path | None:
    for suffix in _ENV_SUFFIXES:
        candidate = root / "env" / f"{env_name}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def resolve_env_name(
    *,
    explicit: str | None = None,
    configured: str | None = None,
    available: list[str] | None = None,
    default: str = DEFAULT_ENV,
) -> str:
    """解析要加载的 env/设备名。

    优先级：CLI 显式 > product.yaml ``env`` > 仅发现一个文件时自动选 > default。
    若已发现 env 文件，解析结果必须在列表中。
    """
    found = list(available or [])
    if explicit:
        name = str(explicit)
    elif configured:
        name = str(configured)
    elif len(found) == 1:
        name = found[0]
    else:
        name = default

    if found and name not in found:
        options = ", ".join(found)
        raise FileNotFoundError(f"Unknown env {name!r}; available: {options}")
    return name


def _host_from_base_url(base_url: str) -> str | None:
    """从 browser.base_url 提取主机名；无效则返回 None。"""
    if not base_url:
        return None
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    return parsed.hostname or None


def _parse_db(raw: dict[str, Any] | None, *, fallback_host: str | None) -> DbSettings:
    """解析 YAML ``db`` 块；省略 host 时回落 base_url 主机，再无则 127.0.0.1。"""
    data = dict(raw or {})
    if not data:
        return DbSettings()
    host = data.get("host")
    if not host:
        host = fallback_host or "127.0.0.1"
    read_timeout = data.get("read_timeout")
    write_timeout = data.get("write_timeout")
    return DbSettings(
        host=str(host),
        port=int(data.get("port", 3306)),
        user=str(data.get("user", "")),
        password=str(data.get("password", "")),
        database=str(data.get("database", "")),
        charset=str(data.get("charset", "utf8mb4")),
        connect_timeout=float(data.get("connect_timeout", 10.0)),
        read_timeout=float(read_timeout) if read_timeout is not None else None,
        write_timeout=float(write_timeout) if write_timeout is not None else None,
        autocommit=bool(data.get("autocommit", True)),
        auto_setup_remote=bool(data.get("auto_setup_remote", True)),
    )


def _parse_ssh(
    raw: dict[str, Any] | None,
    *,
    fallback_host: str | None,
) -> SshSettings:
    """解析 YAML ``ssh`` 块；省略 host 时用 fallback（db.host 或 base_url）。"""
    data = dict(raw or {})
    if not data:
        return SshSettings()
    host = str(data.get("host") or "") or (fallback_host or "")
    return SshSettings(
        host=host,
        port=int(data.get("port", 22)),
        user=str(data.get("user", "")),
        password=str(data.get("password", "")),
        key_filename=str(data.get("key_filename", "")),
        connect_timeout=float(data.get("connect_timeout", 10.0)),
        command_timeout=float(data.get("command_timeout", 120.0)),
    )


def _parse_feishu(raw: dict[str, Any] | None) -> FeishuSettings:
    """解析 YAML ``feishu`` 块；缺省为关闭。"""
    data = dict(raw or {})
    if not data:
        return FeishuSettings()
    return FeishuSettings(
        enabled=bool(data.get("enabled", False)),
        webhook=str(data.get("webhook", "") or ""),
        include_failures=bool(data.get("include_failures", False)),
        failure_limit=int(data.get("failure_limit", 20)),
        timeout_sec=float(data.get("timeout_sec", 5.0)),
    )


def _build_config(data: dict[str, Any]) -> PilotConfig:
    """将已合并的扁平 dict 转为 PilotConfig。"""
    browser_raw = data.get("browser", {}) or {}
    channel = browser_raw.get("channel")
    browser = BrowserSettings(
        browser=browser_raw.get("browser", "chromium"),
        channel=str(channel) if channel else None,
        headless=bool(browser_raw.get("headless", True)),
        slow_mo=int(browser_raw.get("slow_mo", 0)),
        viewport_width=int(browser_raw.get("viewport_width", 1280)),
        viewport_height=int(browser_raw.get("viewport_height", 720)),
        timeout_ms=int(browser_raw.get("timeout_ms", 15_000)),
        navigation_timeout_ms=int(browser_raw.get("navigation_timeout_ms", 30_000)),
        action_retries=int(browser_raw.get("action_retries", 2)),
        action_retry_delay_ms=int(browser_raw.get("action_retry_delay_ms", 400)),
        trace=str(browser_raw.get("trace", "retain-on-failure")),
        screenshot_on_failure=bool(browser_raw.get("screenshot_on_failure", True)),
        video=str(browser_raw.get("video", "off")),
        base_url=str(browser_raw.get("base_url", data.get("base_url", ""))),
    )
    base_host = _host_from_base_url(browser.base_url)
    db = _parse_db(data.get("db"), fallback_host=base_host)
    # ssh.host：显式 > db.host（DB 已启用）> base_url 主机
    if db.enabled and db.host:
        ssh_fallback = db.host
    else:
        ssh_fallback = base_host
    ssh = _parse_ssh(data.get("ssh"), fallback_host=ssh_fallback)
    feishu = _parse_feishu(data.get("feishu"))
    default_account = str(data.get("default_account") or "")
    return PilotConfig(
        env=str(data.get("env", DEFAULT_ENV)),
        browser=browser,
        db=db,
        ssh=ssh,
        feishu=feishu,
        accounts=dict(data.get("accounts", {}) or {}),
        default_account=default_account,
        extras={
            k: v
            for k, v in data.items()
            if k
            not in {
                "env",
                "product",
                "browser",
                "accounts",
                "default_account",
                "base_url",
                "db",
                "ssh",
                "feishu",
            }
        },
    )


def _load_layered(config_dir: Path, env: str | None) -> PilotConfig:
    """加载 product.yaml + env/<name>.yaml。"""
    product_data = _read_yaml(config_dir / "product.yaml")
    # product 里可能仍带 default 键（少见）；扁平字段直接作为共享默认
    data: dict[str, Any] = dict(product_data)
    available = discover_envs(config_dir)
    configured = product_data.get("env")
    env_name = resolve_env_name(
        explicit=env,
        configured=str(configured) if configured is not None else None,
        available=available,
    )
    env_path = _env_file(config_dir, env_name)
    if env_path is not None:
        data = _merge_dict(data, _read_yaml(env_path))
    data["env"] = env if env else env_name
    return _build_config(data)


def _load_legacy_file(config_path: Path, env: str | None) -> PilotConfig:
    """加载单文件：top-level ``default`` + 命名 env 块。"""
    raw = _read_yaml(config_path)
    default = raw.get("default", {})
    env_name = env or raw.get("env", DEFAULT_ENV)
    env_block = raw.get(env_name, {})
    data = _merge_dict(default if isinstance(default, dict) else {}, env_block if isinstance(env_block, dict) else {})
    data.setdefault("env", env_name)
    return _build_config(data)


def _is_layered_config_dir(path: Path) -> bool:
    """目录含 product.yaml 或 env/ 时视为分层配置根。"""
    if not path.is_dir():
        return False
    return (path / "product.yaml").is_file() or (path / "env").is_dir()


def load_config(
    path: str | Path | None = None,
    env: str | None = None,
    *,
    config_dir: str | Path | None = None,
) -> PilotConfig:
    """加载配置。

    - ``config_dir``：分层目录（product.yaml + env/*.yaml）
    - ``path`` 为目录：等同 ``config_dir``
    - ``path`` 为文件：单文件兼容布局
    - 皆空：仅代码默认
    """
    if config_dir is not None:
        return _load_layered(Path(config_dir), env)

    if path is None:
        return _build_config({"env": env or DEFAULT_ENV})

    config_path = Path(path)
    if not config_path.exists():
        return _build_config({"env": env or DEFAULT_ENV})

    if config_path.is_dir() or _is_layered_config_dir(config_path):
        return _load_layered(config_path, env)

    return _load_legacy_file(config_path, env)
