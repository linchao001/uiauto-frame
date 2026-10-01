# Page 层（何时读）

写/改 `pages/*_page.py`、定位或页面操作时读本文件。依赖：已读入口 `README.md` 硬规则。

对照：`pilot init` 生成的 `pages/login_page.py`、`home_page.py`

## 职责

- 继承 `pilot.core.base_page.BasePage`
- **唯一**接触 locator 与 `click`/`fill` 等动作的地方
- **不要**写 `expect_*`（断言在 Check）

## 结构约定

```python
class LoginPage(BasePage):
    path = "/"  # 相对 base_url

    @property
    def username_input(self) -> Locator:
        return self.by_placeholder("请输入账号")

    def wait_ready(self) -> None:
        self.username_input.wait_for(state="visible", timeout=self.settings.timeout_ms)

    def login(self, username: str, password: str) -> None:
        self.fill(self.username_input, username, name="账号")
        self.click(self.login_button, name="登录")
```

- 命名 locator 用 `@property` 声明一次，方法只引用
- `open()`：`goto(domcontentloaded)` → `wait_ready()`；业务打开页面优先走 `open()` 或显式 `open` 等价流程

## `wait_ready`

- **必须覆盖**：等 URL / 关键控件 / 骨架消失等真实信号
- 可用 Playwright 的 `wait_for` / `wait_for_url` 做**流程同步**（不是断言）
- **禁止** `time.sleep`、固定时长轮询

## 定位优先级

1. **一等**：`by_testid` / `by_role` / `by_label`（可控产品优先 testid）
2. **次级**：`by_placeholder` / `by_text` / `by_alt_text` / `by_title`
3. **兜底**：`locator("css")`

字符串快捷（传给动作/部分 API）：`"testid:xxx"` → `get_by_test_id`

## `match` 与列表场景

- 动作默认 `match="strict"`（多匹配立即失败，**不重试**）
- 仅明确需要时：`match="first"|"last"|n`（`n` 为 int 下标）
- 列表/卡片内：优先 `within(root, child)` 或 `filter_has_text`，避免默认 `.first`

```python
row = self.filter_has_text(self.locator(".item"), "订单号")
self.click(self.within(row, "testid:btn-pay"), name="支付")
```

## 动作 API（经 BasePage，带 actionability + 瞬态重试）

| 方法 | 说明 |
|---|---|
| `click(target, *, name=, match=)` | 点击 |
| `fill(target, value, *, name=, match=)` | 填写 |
| `select_option(target, value, *, name=, match=)` | 下拉 |
| `scroll_into_view(target, *, name=, match=)` | 滚入可见；嵌套容器先 `within` |

- `target`：`Locator` 或选择器字符串（含 `testid:`）
- 传 `name=` 便于日志/失败定位
- **禁止**在 `click`/`fill` 前再包一层 `wait_for(state="visible")`

## 等待与重试（Page 侧）

- 操作等待：Playwright actionability；瞬态失败由框架 `retry_action`（半额超时）
- 定位错误（strict 多匹配）立即失败，不重试
- 不要自建 sleep / 手写轮询循环

## 禁令速查

- Page 内 `expect_*` / `assertx`
- 用例或 Action 里直接 `page.locator`
- 无 `wait_ready` 的业务页
