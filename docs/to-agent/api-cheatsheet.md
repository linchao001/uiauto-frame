# API 速查（何时读）

确认「有没有这个方法 / 从哪 import」时读。细节以源码为准。

## 导出与基类

| 符号 | 模块 | 用途 |
|---|---|---|
| `BasePage` | `pilot` / `pilot.core.base_page` | 页面基类 |
| `BaseCheck` | `pilot` / `pilot.core.base_check` | 断言基类 |
| `BaseFlow` | `pilot` / `pilot.flow.base` | Flow 基类 |
| `AuthProvider` / `register_auth_provider` | `pilot.account.auth` | 产品鉴权接口与注册 |
| `cases` / `Case` / `load_cases` | `pilot` / `pilot.cases` | UI 数据驱动 |
| `soft_assertions` / `assert_all` | `pilot.core` / `pilot.core.soft` | 软断言 |
| `assertx` | `pilot.core.assertx` | 底层断言（优先经 BaseCheck） |
| `get_db` | `pilot.db` | 无 fixture 时取 DB |
| `get_ssh` | `pilot.ssh` | 无 fixture 时取 SSH |

## BasePage

| API | 用途 |
|---|---|
| `path` / `url` / `open()` | 路径与打开 |
| `wait_ready()` | 业务就绪（须覆盖） |
| `by_testid/role/label/placeholder/text/alt_text/title` | 定位 |
| `locator(sel)` | CSS 等兜底 |
| `within` / `filter_has_text` / `nth` | 范围与列表 |
| `click` / `fill` / `select_option` / `scroll_into_view` | 动作（`name=` `match=`） |

源码：`src/pilot/core/base_page.py`、`locate.py`

## BaseCheck

| API | 用途 |
|---|---|
| `expect_visible/hidden/text/value/attribute` | UI |
| `expect_count` / `expect_url_contains` | UI |
| `expect_not_none` / `expect_none` | 通用值 |
| `expect_row` / `expect_rows_*` | DB 行 |

源码：`src/pilot/core/base_check.py`

## BaseFlow

| API | 用途 |
|---|---|
| `page` / `config` | 注入给 Actions/Checks |
| `account(role=None)` | 账号 dict；无参用 `default_account`（产品自定） |
| `auth_provider` | 已注入的 `AuthProvider` |
| `open_as(role, page_url)` | 经 AuthProvider.login 后打开页面。`role` 为 accounts key；`page_url` 为路径或绝对 URL。不等 `wait_ready` |
| `step(name)` | 步骤上下文 |
| `spawn()` | 同浏览器再开 Context，返回同型 Flow（仅 cookie 隔离） |
| `spawn_browser(isolated=False)` | 同 Playwright 再 launch Browser（串行真多开） |
| `spawn_browser(isolated=True)` | 专属线程上新建 Playwright + Browser（真并发就绪） |
| `run_concurrent(*fns, timeout=None)` | 多线程齐射；参与方勿共享 Playwright |

产品 demo 另暴露：`login_as("role_a")`（UI 登录）、`open_as("role_a", "home")`（产品解析角色与页面后调用框架 `open_as(account_key, page_url)`）。鉴权须产品实现 `AuthProvider` 并 `register_auth_provider`。

`other = flow.spawn()` 后再各自 `open_as(...)`，得到独立 Context。需要真多开窗口时用 `flow.spawn_browser()`。真并发（两端几乎同时操作）用两路 `spawn_browser(isolated=True)` + `flow.run_concurrent(...)`；主 `flow` 不要进并发工作线程。

源码：`src/pilot/flow/base.py`

## Fixtures / CLI（插件）

| 名称 | 说明 |
|---|---|
| `flow` | 由 `flow_factory` 构造；注入 `auth_provider` |
| `auth_provider` | 已 `register_auth_provider` 的实现；未注册则为 Unset |
| `db` / `ssh` | 配置了才可用 |
| `--env` / `--pilot-env` | 设备 |
| `--pilot-headed` / `--pilot-browser` | 浏览器 |
| `--priority` | P0–P3 过滤 |
| `--pilot-config` | 配置路径 |

源码：`src/pilot/pytest_plugin.py`
