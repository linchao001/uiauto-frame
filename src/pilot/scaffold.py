"""按框架约定生成产品用例仓库骨架。"""

from __future__ import annotations

from pathlib import Path

# 运行产物目录名；agent_docs / hatch 等仍可能引用此常量
SKIP_DIR_NAMES = frozenset(
    {
        ".pytest_cache",
        "__pycache__",
        "reports",
        ".ruff_cache",
        ".mypy_cache",
        ".venv",
    }
)


class ScaffoldError(RuntimeError):
    """创建用例仓库失败（目标非法、产品名无效等）。"""


def resolve_product_name(dest: Path, product: str | None) -> str:
    """``--product`` 优先；否则用目标目录名。"""
    raw = (product if product is not None else dest.name).strip()
    if not raw:
        raise ScaffoldError("产品名不能为空（请传 --product 或使用非空目录名）")
    return raw


def build_case_repo_files(product: str) -> dict[str, str]:
    """返回相对路径 → 文件内容（UTF-8 文本）。"""
    return {
        ".gitignore": _GITIGNORE,
        "conftest.py": _CONFTEST,
        "flow.py": _FLOW,
        "account/__init__.py": '"""产品鉴权实现包。"""\n',
        "account/auth.py": _ACCOUNT_AUTH,
        "pages/__init__.py": '"""页面对象包：唯一接触 Playwright locator 的层。"""\n',
        "pages/home_page.py": _HOME_PAGE,
        "pages/login_page.py": _LOGIN_PAGE,
        "actions/__init__.py": '"""业务 Actions：用例唯一可调用的操作 API。"""\n',
        "actions/auth.py": _AUTH,
        "checks/__init__.py": _CHECKS_INIT,
        "checks/home.py": _HOME_CHECK,
        "cases/test_login.py": _TEST_LOGIN,
        "config/product.yaml": _product_yaml(product),
        "config/env/lab.yaml.example": _LAB_EXAMPLE,
    }


def create_case_repo(
    dest: Path,
    *,
    product: str | None = None,
    force: bool = False,
) -> list[Path]:
    """在 ``dest`` 生成产品仓骨架，返回写入文件的相对路径。

    目标已有文件时默认拒绝；``force`` 只覆盖同名文件，不删多余文件。
    """
    dest = dest.resolve()
    name = resolve_product_name(dest, product)
    if dest.exists() and not dest.is_dir():
        raise ScaffoldError(f"目标不是目录：{dest}")
    if dest.exists() and _has_files(dest) and not force:
        raise ScaffoldError(f"目标目录不是空的：{dest}。如需覆盖同名文件，请加 --force")

    files = build_case_repo_files(name)
    written: list[Path] = []
    for rel, content in sorted(files.items()):
        path = Path(rel)
        target = dest / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def _has_files(dest: Path) -> bool:
    return any(path.is_file() for path in dest.rglob("*"))


def _product_yaml(product: str) -> str:
    return f"""\
product: {product}
env: lab
# 用例默认账号 key（与 accounts 中的 key 对齐）
default_account: test_user
browser:
  browser: chromium
  headless: false
  timeout_ms: 15000
  viewport_width: 1500
  viewport_height: 800
# 鉴权协议由产品实现 AuthProvider（account/auth.py），框架不解析业务鉴权配置
feishu:
  enabled: false
"""


_GITIGNORE = """\
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
test-results/
playwright-report/
reports/

# 设备凭据：只保留 *.yaml.example，本地复制后填写
config/env/*.yaml
config/env/*.yml
!config/env/*.yaml.example
!config/env/*.yml.example
"""

_LAB_EXAMPLE = """\
# 复制为 lab.yaml 后填写真实值（*.yaml 已被 gitignore，勿提交）
#   cp config/env/lab.yaml.example config/env/lab.yaml
browser:
  base_url: https://device.example

accounts:
  test_user:
    username: testuser
    password: changeme

# 鉴权 HTTP / 表名等业务约定写在产品 account/auth.py（或产品自有配置），勿依赖框架解析

ssh:
  user: sshuser
  password: changeme

db:
  port: 3306
  user: dbuser
  password: changeme
  database: app_db
"""

_ACCOUNT_AUTH = '''\
"""产品鉴权：必须实现 AuthProvider，框架不内置业务协议。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pilot.account.auth import AuthProvider

if TYPE_CHECKING:
    from pilot.core.config import PilotConfig
    from pilot.db.client import DbClient


class ProductAuth(AuthProvider):
    """对接本产品登录 / token 存储；按实际协议实现下列方法。"""

    def login(self, *, base_url: str, username: str, password: str) -> dict[str, Any]:
        """接口登录。TODO: 调用产品登录接口并返回结果 dict。"""
        raise NotImplementedError("实现 ProductAuth.login（产品登录接口）")

    def token_store_items(self, login_data: dict[str, Any]) -> dict[str, str]:
        """登录结果 → localStorage 项。TODO: 返回 {storage_key: json_or_value}。"""
        raise NotImplementedError("实现 ProductAuth.token_store_items")

    def recreate_test_account(
        self,
        config: PilotConfig,
        db: DbClient | None,
    ) -> None:
        """可选：会话开始重建测试账号。默认不做事。"""
        return

    def report_version_fields(self, config: PilotConfig) -> dict[str, str]:
        """可选：HTML 报告 Environment 字段。默认空。"""
        return {}
'''

_CONFTEST = '''\
"""注册产品 Flow 与 AuthProvider。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from account.auth import ProductAuth
from flow import Flow
from pilot.account.auth import register_auth_provider
from pilot.core.config import PilotConfig
from pilot.pytest_plugin import _load_pilot_config

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config: pytest.Config) -> None:
    """会话开始前注册鉴权实现（报告版本钩子也依赖此处）。"""
    register_auth_provider(config, ProductAuth())


@pytest.fixture(scope="session")
def pilot_config(pytestconfig: pytest.Config) -> PilotConfig:
    """默认读本仓 config/，IDE 直接跑用例无需 CLI。"""
    cli = pytestconfig.getoption("--pilot-config")
    config_path = Path(cli) if cli else (ROOT / "config")
    return _load_pilot_config(pytestconfig, explicit_config_path=config_path)


@pytest.fixture
def flow_factory():
    """返回 Flow 构造器；pilot 的 flow fixture 会调用它。"""
    return Flow
'''

_FLOW = '''\
"""产品 Flow：组装 Actions 与 Checks。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.auth import PAGE_TO_PATH, AuthActions, resolve_page_path, resolve_role_account_key
from checks import Checks
from pages.home_page import HomePage

from pilot.flow.base import BaseFlow

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from pilot.core.config import PilotConfig


class Flow(BaseFlow):
    """注入用例的 flow：提供 login_as / open_as / auth / check。"""

    def __init__(self, page: Page, config: PilotConfig) -> None:
        super().__init__(page, config)
        # UI 登录动作；接口鉴权在 auth_provider（AuthProvider）
        self.auth = AuthActions(self)
        self.check = Checks(self)

    def login_as(self, role: str) -> None:
        """按角色名走 UI 登录。例：``login_as("role_a")``。"""
        self.auth.login_as(role)

    def open_as(self, role: str, page: str) -> None:
        """角色与页面名解析后，交给框架做接口登录并打开页面 URL。

        例：``open_as("role_a", "home")``。
        """
        account_key = resolve_role_account_key(role)
        path = resolve_page_path(page)
        with self.step(f"接口登录进入:{role}:{page}", report=False):
            super().open_as(account_key, path)
            if path.rstrip("/") == PAGE_TO_PATH["home"].rstrip("/"):
                HomePage(self.page, self.config.browser).wait_ready()

    def login(self, username: str, password: str) -> None:
        """按显式账号密码走 UI 登录（委托 auth）。"""
        self.auth.login(username, password)
'''

_HOME_PAGE = '''\
"""应用 home 页面对象。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pilot.core.base_page import BasePage

if TYPE_CHECKING:
    from playwright.sync_api import Locator


class HomePage(BasePage):
    """登录后的应用落地页。"""

    path = "/home"

    @property
    def ready_marker(self) -> Locator:
        """页面就绪信号。TODO: 换成产品真实定位（优先 testid / role）。"""
        return self.by_testid("home-ready")

    def wait_ready(self) -> None:
        """等落地页关键元素出现。"""
        self.ready_marker.wait_for(state="visible", timeout=self.settings.timeout_ms)
'''

_LOGIN_PAGE = '''\
"""登录页页面对象。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pilot.core.base_page import BasePage

if TYPE_CHECKING:
    from playwright.sync_api import Locator


class LoginPage(BasePage):
    """产品登录页。"""

    path = "/"

    @property
    def username_input(self) -> Locator:
        """账号输入框。TODO: 换成产品真实定位。"""
        return self.by_placeholder("Username")

    @property
    def password_input(self) -> Locator:
        """密码输入框。TODO: 换成产品真实定位。"""
        return self.by_placeholder("Password")

    @property
    def login_button(self) -> Locator:
        """登录按钮。TODO: 换成产品真实定位。"""
        return self.by_role("button", name="Sign in")

    def wait_ready(self) -> None:
        """等账号输入框出现。"""
        self.username_input.wait_for(state="visible", timeout=self.settings.timeout_ms)

    def login(self, username: str, password: str) -> None:
        """填写账号密码并点击登录。"""
        self.fill(self.username_input, username, name="username")
        self.fill(self.password_input, password, name="password")
        self.click(self.login_button, name="sign-in")
'''

_AUTH = '''\
"""认证动作，以及角色 / 页面到账号与 URL 的映射（产品自定）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pages.home_page import HomePage
from pages.login_page import LoginPage

if TYPE_CHECKING:
    from flow import Flow

# 角色名 → accounts 配置 key（产品自定）
ROLE_TO_ACCOUNT: dict[str, str] = {
    "role_a": "test_user",
}

# 页面名 → 路径（按产品路由修改）
PAGE_TO_PATH: dict[str, str] = {
    "home": "/home",
}


def resolve_role_account_key(role: str) -> str:
    """角色名 → accounts key；未知角色抛错。"""
    if role not in ROLE_TO_ACCOUNT:
        known = "、".join(ROLE_TO_ACCOUNT)
        raise KeyError(f"未知角色 {role!r}；可选：{known}")
    return ROLE_TO_ACCOUNT[role]


def resolve_page_path(page: str) -> str:
    """页面名 → URL path；未知页面抛错。"""
    if page not in PAGE_TO_PATH:
        known = "、".join(PAGE_TO_PATH)
        raise KeyError(f"未知页面 {page!r}；可选：{known}")
    return PAGE_TO_PATH[page]


class AuthActions:
    """UI 登录。接口登录进页由框架 ``BaseFlow.open_as`` + AuthProvider 完成。"""

    def __init__(self, flow: Flow) -> None:
        self._flow = flow
        self._login = LoginPage(flow.page, flow.config.browser)
        self._home = HomePage(flow.page, flow.config.browser)

    def login(self, username: str, password: str) -> None:
        """打开登录页、提交凭据，并等到落地页就绪。"""
        with self._flow.step("UI登录", report=False):
            self._login.open()
            self._login.login(username, password)
            self._home.wait_ready()

    def login_as(self, role: str) -> None:
        """按角色走 UI 登录。"""
        account_key = resolve_role_account_key(role)
        account = self._flow.account(account_key)
        self.login(account["username"], account["password"])
'''

_CHECKS_INIT = '''\
"""业务 Checks：用例侧断言（oracle），不写定位细节。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from checks.home import HomeCheck

if TYPE_CHECKING:
    from flow import Flow


class Checks:
    """聚合各域 Check；用例统一走 flow.check.*。"""

    def __init__(self, flow: Flow) -> None:
        self._home = HomeCheck(flow)

    def home_ready(self) -> None:
        """断言已进入应用落地页。"""
        self._home.home_ready()
'''

_HOME_CHECK = '''\
"""落地页相关断言。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pages.home_page import HomePage
from pilot.core.base_check import BaseCheck

if TYPE_CHECKING:
    from flow import Flow


class HomeCheck(BaseCheck):
    """落地页就绪等断言；用例通过 flow.check 调用。"""

    def __init__(self, flow: Flow) -> None:
        super().__init__(flow.page, flow.config.browser)
        self._home = HomePage(flow.page, flow.config.browser)

    def home_ready(self) -> None:
        """断言已进入落地页（URL + 就绪标记）。"""
        self.expect_url_contains("/home")
        self.expect_visible(self._home.ready_marker)
'''

_TEST_LOGIN = '''\
"""登录冒烟：test_user 进入落地页。"""

from __future__ import annotations

import pytest


@pytest.mark.P0
@pytest.mark.case_title(case_id="UI-01", title="role_a 登录成功进入 home")
def test_role_a_login(flow) -> None:
    """role_a UI 登录成功后应进入落地页。

    首次跑通前请：复制 lab.yaml.example → lab.yaml，实现 account/auth.py，并补齐 Page 定位。
    """
    flow.login_as("role_a")
    flow.check.home_ready()
'''
