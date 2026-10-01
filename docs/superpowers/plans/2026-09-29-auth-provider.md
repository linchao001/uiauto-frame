# AuthProvider 外置鉴权 Implementation Plan

> 状态：已实现。保留作归档；细节以当前源码与 `docs/to-agent` 为准。

**Goal:** 框架鉴权只保留 `AuthProvider` 基类与挂钩；产品仓自行实现协议；scaffold/docs 用中性示例。

**Architecture:** ABC `AuthProvider` + `register_auth_provider`（pytest stash）；`BaseFlow.open_as` / 会话建号 / 报告版本均调用 Provider。

**Spec:** `docs/superpowers/specs/2026-09-29-auth-provider-design.md`

## Global Constraints

- 框架源码与可提交模板不出现具体业务鉴权字段名、路径、表名、中文业务角色
- 中文 docstring（项目规则）
- 单测假数据保持中性，不模仿真实产品协议

---

### Task 1: AuthProvider ABC + Unset 哨兵 — 完成

- `src/pilot/account/auth.py`：`AuthProvider` / `UnsetAuthProvider` / `register_auth_provider`
- 必选：`login`、`token_store_items`；可选：`recreate_test_account`、`report_version_fields`
- 测试：`tests/test_auth_provider.py`

### Task 2: BaseFlow 注入 AuthProvider — 完成

- `BaseFlow.open_as(account_key, page_url)` 调 Provider
- FakeAuthProvider 覆盖 `tests/test_flow_open_as.py`

### Task 3: pytest 注册 + 建号/版本挂钩 — 完成

- `register_auth_provider` + stash；`pilot_recreate_test_account`；报告版本经 Provider
- `tests/test_recreate_test_account.py`、`tests/test_report_version.py`

### Task 4: 去掉框架内置鉴权实现 — 完成

- 无产品鉴权模块 / 配置 schema；未知 YAML 键进 `extras`
- `default_account` 默认空字符串

### Task 5: Scaffold 中性骨架 — 完成

- `account/auth.py` stub + conftest 注册
- 角色/页面：`role_a` / `home`；账号：`test_user`

### Task 6: 文档与单测去业务化 — 完成

- to-agent / README：AuthProvider 必做 + 中性示例
- HTTP/storage 等单测使用中性假路径与字段

## Spec coverage

| Spec 项 | Task |
|---------|------|
| AuthProvider ABC | 1 |
| open_as 走 Provider | 2 |
| 注册 / recreate / report | 3 |
| 去掉内置鉴权实现 | 4 |
| scaffold + 中性名 | 5 |
| to-agent / 单测去业务化 | 6 |
