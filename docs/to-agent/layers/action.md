# Action / Flow 层（何时读）

写/改 `actions/` 或 `flow.py` 时读本文件。依赖：Page 层已按 `page.md` 写好。

对照：`pilot init` 生成的 `actions/auth.py`、`flow.py`

## Actions 职责

- 表达**业务步骤**（登录、下单…），不写断言
- 内部创建/持有 Page，只调 Page 方法
- 用例不直接 import Actions；经 `flow` 暴露

```python
class AuthActions:
    def __init__(self, flow: Flow) -> None:
        self._flow = flow
        self._login = LoginPage(flow.page, flow.config.browser)
        self._home = HomePage(flow.page, flow.config.browser)

    def login(self, username: str, password: str) -> None:
        # Action 内部过程：仅日志（中文步骤名），不进报告
        with self._flow.step("UI登录", report=False):
            self._login.open()
            self._login.login(username, password)
            self._home.wait_ready()  # 流程同步，不是 expect_*

    def login_as(self, role: str) -> None:
        # 角色名由产品 ROLE_TO_ACCOUNT 映射
        ...
```

## 约定

- 用 `with flow.step("中文名", report=False):` 包 Action 内部过程（**只写日志**，步骤名用中文）
- 报告步骤留给用例：`with flow.step("操作原文 → 预期原文"):`（默认 `report=True`）
- **进页**：非登录页回归用 `flow.open_as("role_a", "home")`。产品只把解析后的账号 key 和页面 URL 传给 `BaseFlow.open_as`（依赖已注册的 `AuthProvider.login`）；登录页回归用 `flow.login_as("role_a")`
- **独立浏览器会话**：仅 cookie 隔离用 `flow.spawn()`；串行真多开用 `flow.spawn_browser()`；真并发用 `flow.spawn_browser(isolated=True)` + `flow.run_concurrent(...)`，再各自 `open_as` / `login_as`
- 角色 / 页面映射写在 `actions/auth.py`（`ROLE_TO_ACCOUNT`、`PAGE_TO_PATH`）；未知角色或页面抛 `KeyError`
- **鉴权**：产品必须实现 `AuthProvider`（`login` + `token_store_items`）并在 conftest `register_auth_provider`；可选覆盖 `recreate_test_account` 做会话建号
- 跨页流程在 Action 内串联多个 Page；打开后落到目标页的 `wait_ready`
- **不要**在 Action 里写 `expect_*`（交给 Check）

## Flow 组装

产品仓继承 `pilot.flow.base.BaseFlow`，在 `__init__` 挂 Actions / Checks，并提供用例友好方法：

```python
class Flow(BaseFlow):
    def __init__(self, page: Page, config: PilotConfig) -> None:
        super().__init__(page, config)
        self.auth = AuthActions(self)  # UI 动作；勿覆盖 auth_provider
        self.check = Checks(self)

    def login_as(self, role: str) -> None:
        self.auth.login_as(role)

    def open_as(self, role: str, page: str) -> None:
        # 只解析角色与页面 URL，接口登录和跳转交给 BaseFlow.open_as
        account_key = resolve_role_account_key(role)
        path = resolve_page_path(page)
        super().open_as(account_key, path)
```

`BaseFlow` 已提供：

| 成员 | 用途 |
|---|---|
| `page` / `config` | 供 Actions/Checks 构造 Page |
| `auth_provider` | 已注入的 `AuthProvider`（pytest flow fixture 设置） |
| `account(role=None)` | 取账号 dict；无参用 `default_account` |
| `open_as(role, page_url)` | 经 AuthProvider.login 后打开页面。`role` 为 accounts key；`page_url` 为路径或绝对 URL。不等 `wait_ready` |
| `step(name)` | 步骤上下文管理器 |
| `spawn()` | 同浏览器新 Context → 同型 Flow（仅 cookie 隔离） |
| `spawn_browser(isolated=False)` | 同 Playwright 再 launch Browser → 同型 Flow |
| `spawn_browser(isolated=True)` | 专属线程新建 Playwright + Browser（并发就绪） |
| `run_concurrent(*fns, timeout=None)` | 多线程齐射；参与方勿共享 Playwright |

## conftest 注册

```python
def pytest_configure(config):
    register_auth_provider(config, ProductAuth())

@pytest.fixture
def flow_factory():
    return Flow  # pilot 插件用其构造 flow fixture
```

对照：`pilot init` 生成的 `conftest.py`、`account/auth.py`

## 禁令速查

- Action 内直接断言或操作裸 `locator`（应走 Page 方法）
- 把 Playwright 细节泄漏到 `flow` 的用例 API 上
- 用例 `from actions...` 绕过 Flow
