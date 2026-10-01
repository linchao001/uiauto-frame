# Check 层（何时读）

写/改 `checks/` 或业务断言时读本文件。依赖：Page 已有命名 locator。

对照：`pilot init` 生成的 `checks/home.py`、`checks/__init__.py`

## 职责

- 业务断言（oracle）；用例通过 `flow.check.*` 调用
- 继承 `pilot.core.base_check.BaseCheck`
- UI / DB / 通用值统一 `self.expect_*`（底层 `pilot.core.assertx`）
- **Page 禁止** `expect_*`；Check **借用** Page 的命名 locator，不在 Check 里散落 CSS（复杂定位仍放 Page）

```python
class HomeCheck(BaseCheck):
    def __init__(self, flow: Flow) -> None:
        super().__init__(flow.page, flow.config.browser)
        self._home = HomePage(flow.page, flow.config.browser)

    def home_ready(self) -> None:
        self.expect_url_contains("/app/home")
        self.expect_visible(self._home.start_meeting_button)
```

聚合后挂到 Flow：

```python
class Checks:
    def __init__(self, flow: Flow) -> None:
        self._home = HomeCheck(flow)

    def home_ready(self) -> None:
        self._home.home_ready()
```

## UI `expect_*`（常用）

| 方法 | 说明 |
|---|---|
| `expect_visible(target, *, timeout=, match=, message=)` | 可见 |
| `expect_hidden(..., message=)` | 隐藏 |
| `expect_text(target, text, ..., message=)` | 文本 |
| `expect_value(target, value, ..., message=)` | 输入 value |
| `expect_attribute(target, name, value, ..., message=)` | 属性 |
| `expect_count(target, count, ..., message=)` | 匹配数量（不应用 match 收窄） |
| `expect_url_contains(fragment, ..., message=)` | URL 包含 |

- `target`：`Locator | str`；默认 `match="strict"`
- `timeout` 默认 `settings.timeout_ms`；Playwright expect **内置轮询**，无断言级 retry
- `message`：可选业务失败提示；失败时还会自动归类原因（元素未找到 / 值不正确等）并附期望 vs 实际

## 软断言

```python
from pilot.core import soft_assertions

with soft_assertions():
    self.expect_visible(a)
    self.expect_text(b, "x")
# 退出 with 时汇总抛出；可中途 assert_all()
```

- **禁止嵌套** `soft_assertions`
- `with` 外仍为硬断言（失败立即抛）
- 导入：`from pilot.core import soft_assertions`（或 `assert_all`）

## DB / 值断言

Check 上同样有：`expect_not_none` / `expect_none` / `expect_row` / `expect_rows_*`  
落库查询用 fixture `db` 或 `get_db()`；细节见 [`../optional.md`](../optional.md)。

## 禁令速查

- 在 Page / Action / Case 里直接 `assertx.expect_*` 绕过业务 Check（简单值断言除外且应少用）
- Check 内 `time.sleep` 等落库（应用 `db.wait_*`）
- 用 Check 做点击/填写（那是 Page/Action）
