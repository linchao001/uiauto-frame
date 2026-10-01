# Case 层（何时读）

写/改 `cases/test_*.py` 时读本文件。依赖：Flow 已暴露所需 API。

对照：`pilot init` 生成的 `cases/test_login.py`

## 职责

- **只编排** `flow.*`：动作 + `flow.check.*`
- 不碰 `page` / locator / Playwright
- 一条用例一个业务意图；稳定、可读的函数名与 docstring
- **步骤原文**：有文字用例时，docstring 写 `case_id` + `case_title`；`with flow.step("操作原文 → 预期原文"):` 包对应编排（写入报告；step 名同时含步骤与预期）；原文没有的环境兜底单独旁注。Action 内部 `flow.step(..., report=False)` 只进日志。
- **一次性数据**：只在单条用例里用的样例值直接写字面量，不要提成模块常量

```python
@pytest.mark.P0
def test_profile_smoke(flow) -> None:
    """非登录业务：接口登录后直达页面，禁止 login_as。"""
    flow.open_as("role_a", "home")
    flow.check.home_ready()


@pytest.mark.P0
def test_role_a_login(flow) -> None:
    """登录类：走登录页。"""
    flow.login_as("role_a")
    flow.check.home_ready()


@pytest.mark.P1
def test_two_users_concurrent(flow) -> None:
    """单用例再开独立 Context，互不顶票。"""
    left = flow
    other = flow.spawn()
    left.open_as("role_a", "home")
    other.open_as("role_a", "home")
    left.check.home_ready()
    other.check.home_ready()


@pytest.mark.P1
def test_two_browsers_concurrent(flow) -> None:
    """真多开窗口 / 进程隔离用 spawn_browser；仅 cookie 隔离仍用 spawn。"""
    left = flow
    other = flow.spawn_browser()
    left.open_as("role_a", "home")
    other.open_as("role_a", "home")
    left.check.home_ready()
    other.check.home_ready()


@pytest.mark.P1
def test_two_browsers_parallel(flow) -> None:
    """真并发：每路独立 Playwright，再 run_concurrent。"""
    a = flow.spawn_browser(isolated=True)
    b = flow.spawn_browser(isolated=True)
    flow.run_concurrent(
        lambda: a.open_as("role_a", "home"),
        lambda: b.open_as("role_a", "home"),
    )
    a.check.home_ready()
    b.check.home_ready()
```

## 标记

| 标记 | 用途 |
|---|---|
| `@pytest.mark.P0`–`P3` | 优先级；**每个用例最多一个** |
| `@pytest.mark.device("env名")` | 仅在对应设备下收集；名字须与 `config/env` 文件名一致（见 [`../config-run.md`](../config-run.md)） |
| `@pytest.mark.smoke` 等 | 产品自定，需在 pytest.ini 声明 |

## 数据驱动

- 同 UI 流程、多组 input/expect → `@cases("相对用例文件的 yaml")`（见 [`../optional.md`](../optional.md)）
- **禁止**在用例里 `for` 多组数据（必须展开成独立 node）
- 设备 / 优先级标记写在 Python 上，**不写入** YAML

## 禁令速查

- `flow.page` / `page.locator` / 直接 `expect(`
- 用例内造 locator、sleep、自己启浏览器（多用户用 `flow.spawn()` / `flow.spawn_browser()` / `isolated=True` + `run_concurrent`）
- 把断言逻辑写在 case 里而不走 `flow.check`（除非临时调试且应立刻下沉）
