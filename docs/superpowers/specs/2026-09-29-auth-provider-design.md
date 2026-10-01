# 鉴权外置为 AuthProvider（框架仅基类/接口）

日期：2026-09-29  
状态：已实现

## 背景与目标

鉴权 HTTP/DB 约定因产品而异；若写进框架内核，换产品即不可用，也会在可发布包中暴露业务形状。

**目标：** 对外发布的框架在鉴权上**只提供基类/接口与挂钩点**；产品仓自行实现协议。框架源码、可提交模板与文档中**不出现**具体业务鉴权约定（路径、请求头、响应字段、表名、角色中文名等）。

**非目标：** 不在框架内用 YAML「通用化」某产品协议；不做多产品鉴权适配器注册中心。

## 成功标准

1. `src/pilot/` 无登录/建号等具体 HTTP 或业务响应字段实现；不解析产品鉴权配置块。
2. 产品通过实现 `AuthProvider` 完成：接口登录、token→浏览器存储、可选会话建号、可选报告版本字段。
3. 未注册 Provider 时，`open_as` 等挂钩给出明确错误，不静默打错误接口。
4. `pilot init` 生成可编译的 stub + 注册样例；to-agent 文档写明「鉴权必须产品实现」。
5. 框架测试用 FakeAuthProvider 与中性假路径/字段，不模仿真实产品协议。

## 架构

```
用例 / BaseFlow.open_as
        │
        ▼
  AuthProvider（产品实现）
        │
        ├── login
        ├── token_store_items → install_local_storage
        ├── recreate_test_account（可选）
        └── report_version_fields（可选）

框架仍提供：post_json、DbClient、install_local_storage、accounts 字典、Flow 编排
```

框架只约定**基础登录**（账号密码），不含产品特有登录形态。

## 接口设计

`pilot.account.auth.AuthProvider`（ABC）：

| 方法 | 是否必须 | 语义 |
|------|----------|------|
| `login(*, base_url, username, password) -> dict` | 是 | 接口登录；返回产品自定义结构（框架不解释字段） |
| `token_store_items(login_data) -> dict[str, str]` | 是 | 返回写入浏览器存储的 `{storage_key: value}`；value 多为 JSON 字符串 |
| `recreate_test_account(config, db) -> None` | 否，默认 no-op | 会话开始重建测试账号；需要时产品覆盖 |
| `report_version_fields(config) -> dict[str, str]` | 否，默认 `{}` | HTML 报告 Environment 附加字段 |

约束：

- 抽象方法 docstring 用中文说明职责与「产品必须实现」。
- 框架**不**定义 token 字段名、账号主键、表名、登录路径等常量。

## 注册与挂钩

### 注册

产品在 `conftest.py` 的 `pytest_configure` 中调用：

```python
register_auth_provider(config, ProductAuth())
```

未注册时返回 `UnsetAuthProvider`：必选方法抛出含实现指引的 `RuntimeError`。

### `BaseFlow.open_as`

- 签名：`open_as(account_key: str, page_url: str)`（账号 key + 页面 URL；角色名由产品侧自行映射）。
- 从 `config.accounts[account_key]` 取 `username`/`password`，调 `login` → `token_store_items` → 写入存储 → `goto`。
- Flow 经构造或 stash 取得 `AuthProvider`；缺失则报错。

### 会话建号

```text
pilot_recreate_test_account:
  provider = get_auth_provider(config)
  provider.recreate_test_account(pilot_config, db_or_none)
```

`db`：若 `pilot_config.db.enabled` 则注入 `db` fixture，否则 `None`。默认 no-op 不碰库。

### 报告版本

`fill_report_version` 调用 `provider.report_version_fields(config)`，合并进 metadata；空 dict 则跳过。

## 框架边界

### 不进入框架

- 任何产品登录 URL、请求体/响应字段名、建删用户流程
- 产品鉴权专用配置 schema 与解析器

### 保留（通用能力）

- `pilot.core.http.post_json` / `HttpError`
- `pilot.core.storage.install_local_storage`
- `PilotConfig.accounts` / `default_account`（通用账号字典；默认 `""`，不预设角色 key）
- DB/SSH 客户端

### 产品侧

产品仓实现 `AuthProvider` 子类；业务路径与字段放在产品模块常量或产品自有 YAML。

## Scaffold 与文档

### `pilot init`

- 生成 `account/auth.py`：`ProductAuth(AuthProvider)` stub（必选方法 `NotImplementedError`）。
- `conftest.py`：`register_auth_provider(config, ProductAuth())`。
- Demo 用中性名：`role_a` / `home` / `test_user`。
- `lab.yaml.example` 无鉴权协议块；账号仅为占位凭据。

### to-agent

`config-run.md`、`README.md`、`action.md`、`case.md`、`api-cheatsheet.md`：AuthProvider 必做清单 + 中性示例（如 `flow.open_as("role_a", "home")`）。

## 测试约定

| 区域 | 要求 |
|------|------|
| AuthProvider / open_as | Fake provider；测挂钩，不测具体 HTTP 协议 |
| HTTP / storage 单测 | 中性路径与字段（如 `/echo`、`session`） |
| Scaffold | 生成含 AuthProvider stub；可提交配置无业务鉴权块 |
| 未知 YAML 顶层键 | 进入 `extras`，框架不解析 |

## 风险

| 风险 | 缓解 |
|------|------|
| 破坏已依赖内置鉴权的产品仓 | 文档写迁移；版本按 breaking 发布 |
| 建号需要 db 但默认 no-op | 传 `db=None` 或按需注入；产品实现负责 |
