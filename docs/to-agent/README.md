# Pilot — Agent 写 UI 用例入口

**默认只读本文件。** 写到哪一层再打开对应专题；勿通读整目录。

已安装框架时优先走 CLI（`docs/to-agent` 打在包里，不依赖本仓库路径）：

```bash
pilot docs                  # 索引：该读哪一篇
pilot docs show <id>        # 只打印这一篇
pilot docs search <关键词>  # 定位到文件与行
```

id：`readme` `page` `action` `check` `case` `config` `api` `optional`。`readme` 就是本文件。

新产品仓用 `pilot init` 生成骨架；本目录只约定写法，不附带业务样例。

## 阅读协议

1. 先读本文件（硬规则 + 分层 + 最小步骤）
2. 按任务打开下表文件；方法名不确定 → `api-cheatsheet.md`
3. DB / SSH / `@cases` / 飞书 / 报告 → 仅看 `optional.md` 短索引
4. 细节以 `src/pilot/` 源码为准；本目录防漏约定，不替代源码

| 你在做什么 | 打开 |
|---|---|
| 页面定位 / 操作 / `wait_ready` | [`layers/page.md`](layers/page.md) |
| 业务 Actions / Flow 组装 | [`layers/action.md`](layers/action.md) |
| 业务断言 / soft | [`layers/check.md`](layers/check.md) |
| 写 `cases/` 用例 | [`layers/case.md`](layers/case.md) |
| 用例仓库配置 | [`config-run.md`](config-run.md) |
| API 签名速查 | [`api-cheatsheet.md`](api-cheatsheet.md) |
| 可选能力 | [`optional.md`](optional.md) |

## 硬规则

1. **一产品一仓**：产品仓自备 `pages/` `actions/` `checks/` `cases/` `flow.py` `config/` `conftest.py`
2. **用例禁止**直接使用 `page` / `locator` / Playwright API；只编排 `flow.*`
3. **定位与操作只在 Page**；Actions 只调 Page；断言只在 Check（`BaseCheck.expect_*`）；**`BasePage` 无 `expect_*`**
4. **禁止**硬编码 `sleep`、手写轮询；禁止动作前再包 `wait_for(visible)`（与 Playwright actionability 重复）
5. **业务 Page 必须覆盖 `wait_ready()`**（关键控件 / URL / 接口就绪，禁止固定等待）
6. **定位优先级**：`by_testid` / `by_role` / `by_label` → placeholder/text/… → `locator(CSS)` 兜底；默认 `match="strict"`，慎用 `first|last|n`
7. **软断言**只用 `with soft_assertions():`，**禁止嵌套**；作用域外仍是硬断言
8. **账号 / 进页 / 鉴权**：产品必须实现 `AuthProvider`（`account/auth.py`）并 `register_auth_provider`。用例角色由产品映射，例如 `open_as("role_a", "home")` / `login_as("role_a")`。禁止无参 `open_as()`。`flow.spawn()` 只再开独立 Context；需要独立浏览器进程用 `flow.spawn_browser()`；真并发用 `spawn_browser(isolated=True)` + `flow.run_concurrent(...)`（主 `flow` 不进并发线程）。不要在同一 page 上连续接口登录
9. **同流程多组数据**用 `@cases`（见 `optional.md`），禁止用例内 `for` 灌多组
10. **不要改框架内核**来「顺便」写产品用例；只扩展产品仓分层

## 分层职责

| 层 | 职责 | 用例能否直接碰 |
|---|---|---|
| `pages/` | 命名 locator、fill/click、`wait_ready` | 否 |
| `actions/` | 业务动作；`flow.step`；调 Page | 否（经 flow） |
| `checks/` | 业务断言；`BaseCheck.expect_*` | 否（经 `flow.check`） |
| `flow.py` | 组装 Actions/Checks，暴露用例 API | fixture `flow` |
| `cases/` | 编排 `flow.*` + mark | 是 |

## 新增一条业务能力（最小步骤）

1. `pages/`：命名 locator + 操作 + `wait_ready` → 读 `layers/page.md`
2. `actions/`：业务方法，内部 `with flow.step(...)`，只调 Page → `layers/action.md`
3. `checks/`：业务断言 → `layers/check.md`；挂到 `flow.check`
4. `flow.py`：组装并暴露用例可用方法（如 `login_as` / `check.home_ready`）
5. `cases/`：`def test_*(flow):` 只调 `flow.*`，打 `P0`–`P3` → `layers/case.md`
6. 改设备或配置字段 → `config-run.md`；不确定 API → `api-cheatsheet.md`

骨架对照：用 ``pilot init`` 生成产品仓后看 ``pages/`` → ``actions/auth.py`` → ``checks/`` → ``flow.py`` → ``cases/``。

## 自检（写完必过）

- [ ] 用例文件无 `page.` / `locator(` / 直接 `expect(`
- [ ] 新 Page 有 `wait_ready`；新断言走 `flow.check` / `BaseCheck`
- [ ] 分层落点与 `pilot init` 骨架一致（pages / actions / checks / flow / cases）
