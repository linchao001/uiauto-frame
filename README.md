# Pilot Framework

面向多产品复用的 Web UI 自动化框架。用例层只编排业务 Actions，定位/等待/重试/失败留证由框架兜底。

## 鉴权（产品必做）

框架**不内置**任何业务登录协议。接口登录、`open_as` 注 token、可选会话建号 / 报告版本，一律由产品实现 `AuthProvider`。框架只约定**基础登录**（账号密码；不含产品特有登录形态）。

**1. 实现**（`pilot init` 已生成 `account/auth.py` 骨架）：

```python
from pilot.account.auth import AuthProvider

class ProductAuth(AuthProvider):
    def login(self, *, base_url: str, username: str, password: str) -> dict:
        """调用产品登录接口，返回自定义结果（框架不解析字段）。"""
        ...

    def token_store_items(self, login_data: dict) -> dict[str, str]:
        """登录结果 → 浏览器存储：``{storage_key: value}``（value 多为 JSON 字符串）。"""
        ...

    # 可选
    def recreate_test_account(self, config, db) -> None:
        """会话开始重建测试账号；默认 no-op。"""
        ...

    def report_version_fields(self, config) -> dict[str, str]:
        """写入 HTML 报告 Environment；默认 {}。"""
        return {}
```

**2. 注册**（`conftest.py`）：

```python
from account.auth import ProductAuth
from pilot.account.auth import register_auth_provider

def pytest_configure(config):
    register_auth_provider(config, ProductAuth())
```

**3. 用例侧**：角色 / 页面名由产品 `actions/auth.py` 映射；框架 `BaseFlow.open_as(account_key, page_url)` 只调已注册的 Provider。

```python
flow.open_as("role_a", "home")   # 接口登录 + 注 token + 打开页
flow.login_as("role_a")          # UI 登录页（产品 AuthActions）
```

未注册或未实现时，`open_as` 会明确报错并提示实现 `AuthProvider`。细节见 [docs/to-agent/config-run.md](docs/to-agent/config-run.md)。

## 设计原则

- **一个用例仓库 = 一个产品**；本仓库提供可安装的通用框架内核
- 用例禁止直接使用 `page` / `locator`，只通过 `flow.*` 业务动作编写
- 稳定性下沉：统一等待、操作重试、页面 `wait_ready`、失败截图与 Trace
- 页面/DB 断言统一经 **`BaseCheck.expect_*`**（底层 `pilot.core.assertx`）；`BasePage` 不含 `expect_*`
- 软断言：`with soft_assertions():` 内现有 `expect_*` 自动收集失败，退出（或 `assert_all()`）时一次性抛出；禁止嵌套
- DB：YAML 配 `db` → fixture `db` / `get_db()` 做 CRUD；落库用 `BaseCheck.expect_row` / `assertx.expect_row` 等；异步用 `db.wait_*`
- SSH：YAML 配 `ssh` → fixture `ssh` / `get_ssh()`；DB 首次连不上时可自动开 MariaDB 远程访问

## 定位约定

- **一等：** `by_testid` / `by_role` / `by_label`（可控产品优先 testid；有无障碍语义时用 role/label）
- **次级：** `by_placeholder` / `by_text` / `by_alt_text` / `by_title`
- **兜底：** `locator(selector)`（CSS 等）
- 动作与单元素断言默认 **strict**（多匹配即失败）；仅在明确需要时使用 `match="first"|"last"|n`
- 列表/卡片内操作优先 `within(root, child)` 或 `filter_has_text`，避免默认 `.first`
- 字符串快捷：`testid:xxx`

Agent 写用例时的定位约定见 [docs/to-agent/layers/page.md](docs/to-agent/layers/page.md)。

## 等待与重试

框架**不**自建 `sleep` / 手写轮询循环；等待由 Playwright 内置能力承担，外层仅对瞬态操作失败做短重试。

| 场景 | 机制 |
|---|---|
| 操作 `click` / `fill` / `select_option` / `scroll_into_view` | Playwright actionability 自动等待 + `retry_action`（仅 Timeout / detach / intercept / not stable） |
| 断言 `expect_*` | Playwright `expect` 在 `timeout_ms` 内自动轮询；**无**断言级 retry |
| 软断言 `soft_assertions` | `with` 内 `expect_*` 失败继续执行，退出或 `assert_all()` 汇总抛出；`with` 外仍为硬断言 |
| DB 落库 | `db.select_one` + `assertx.expect_row` / `expect_rows_*`（走同一 soft 调度） |
| DB 异步 | `db.wait_present` / `wait_absent` / `wait_count` / `wait_field`（poll，禁止硬 sleep） |
| 页面打开 | `goto(domcontentloaded)` → `wait_ready()` |
| 定位错误（如 strict 多匹配） | **立即失败**，不重试，避免拖长失败并掩盖原因 |

约定：

- 首次操作超时用满 `timeout_ms`，重试用半额超时，控制最坏墙钟时间
- **禁止**在动作前再包一层 `wait_for(visible)`（与 actionability 重复，且会把「被遮挡 / 未启用」伪装成「不可见」）
- 业务 Page **应覆盖** `wait_ready()`：等关键选择器 / 接口完成 / 骨架屏消失等真实就绪信号，不要用固定 `sleep`

## 快速开始

```bash
# 创建并激活虚拟环境后
pip install -e .
# 下载 Playwright 浏览器（如需）
playwright install chromium

# 运行框架单元测试
pytest
```

## DB 落库

`config/env.yaml`：

```yaml
default:
  browser:
    base_url: https://device.example
  ssh:
    # host 可省略：回落 db.host / base_url
    user: sshuser
    password: changeme
  db:
    # host 可省略：回落 base_url 主机
    user: dbuser
    password: changeme
    database: app_db
    # auto_setup_remote: true   # 默认；首次 TCP 失败且配了 ssh 时自动开通
```

> 设备凭据与真实业务接口路径只放本地 `config/env/<device>.yaml`（已 gitignore）。仓库内保留 `*.yaml.example` 模板。

用例：

```python
from pilot.core import assertx

def test_create_order(flow, db):
    flow.order.create(sku="SKU-001")
    row = db.select_one("orders", where={"sku": "SKU-001"})
    assertx.expect_not_none(row)
    assertx.expect_row(row, {"sku": "SKU-001", "status": "pending"})
```

actions / helpers 不便注入 fixture 时用 `from pilot.db import get_db`。

## SSH

```python
def test_remote_uname(ssh):
    result = ssh.run("uname -a", check=True)
    assert "Linux" in result.stdout

def test_restart_service():
    from pilot.ssh import get_ssh
    get_ssh().sudo("systemctl restart nginx")
```

有头模式：

```bash
pytest --pilot-headed
```

## 多设备 / 多浏览器

**设备 = 实验室机型/靶机**（独立 `base_url` / ssh / db），**不是** Playwright 手机模拟。多浏览器走 **CI 多 Job**，进程内不做矩阵 parametrize。

### 配置布局（推荐）

```text
config/
  product.yaml              # 共享默认 + 默认 env
  env/
    lab-a.yaml.example      # 可提交的模板
    lab-a.yaml              # 本地真值（gitignore）
    lab-b.yaml.example
```

`config/product.yaml`：

```yaml
product: demo
env: lab-a             # --env 省略时的默认设备
browser:
  browser: chromium
  headless: true
  timeout_ms: 15000
feishu:
  enabled: false
# 鉴权协议由产品 AuthProvider 实现，框架不解析业务鉴权配置
```

`config/env/lab-a.yaml`（本地，由 example 复制）：

```yaml
browser:
  base_url: https://lab-a.example
ssh:
  user: sshuser
  password: changeme
db:
  user: dbuser
  password: changeme
  database: app_db
```

加载顺序：代码默认 < `product.yaml` < `env/<name>.yaml` < CLI。

仍兼容旧版单文件 `config/env.yaml`（`default` + 命名块）。

### 切换设备

```bash
pytest --env lab-b
pytest --pilot-env lab-a       # 等价
```

机型专属用例：

```python
@pytest.mark.device("lab-a")
def test_only_on_lab_a(flow):
    ...
```

未标记的用例在所有设备上执行；有 `device` 标记的仅在列出的 `--env` 下收集。

### 优先级

合法标记：`@pytest.mark.P0` / `P1` / `P2` / `P3`（每个用例只能打一个）。

```python
@pytest.mark.P0
def test_critical_login(flow):
    ...
```

筛选：

```bash
pytest --priority P0              # 仅 P0；未打 P0–P3 的用例会被剔除
pytest --priority P0,P1           # 多个级别逗号分隔（CLI 大小写不敏感）
pytest -m P0                      # 原生 -m，可与其它 mark 组合：-m "P0 and smoke"
```

未传 `--priority` 时不按优先级过滤。同一用例多个优先级标记、或 CLI 非法级别，在收集阶段直接失败。

### 多浏览器（CI Job）

```bash
pytest --pilot-browser=chromium
pytest --pilot-browser=firefox
pytest --pilot-browser=webkit
```

CI 用 `matrix.env × matrix.browser`，每个 Job 一次 pytest；本地默认仍单浏览器。

## 测试报告

用 ``--report`` 一键生成自包含增强 HTML：

```bash
# 推荐：按环境归档
pytest --env lab --report
# → reports/lab/<YYYYMMDD_HHMMSS>/report.html
# 同目录上级 latest.json 指向最近一次

# 改根目录
pytest --report --report-dir ./artifacts/reports

# 只重跑某次报告中的 Failed/Error（PATH=report.html 或 run 目录；不依赖 --lf）
pytest --from-report reports/lab/20260924_120000/report.html --env lab --report
pytest --from-report reports/lab/20260924_120000 --env lab --report

# 或手写路径（仍支持失败附件挂载）
pytest --html=reports/report.html --self-contained-html

# Allure
pytest --alluredir=reports/allure-results
allure serve reports/allure-results
```

有 HTML 报告时，框架在开测前合并 ``AuthProvider.report_version_fields`` 到 Environment（未实现或失败不阻断）。
报告结果表会多 Case ID / Priority / Title 列（来自 ``@pytest.mark.case_title`` 与 P0–P3）；
``flow.step(...)``（默认）步骤会出现在 Title 悬停与详情区；Action 内 ``report=False`` 仅打日志。失败截图/trace/录像只在 ``--report`` 时落在本次报告目录 ``artifacts/`` 下，报告内可点击查看；未开报告不生成这些产物。

``--from-report`` 解析指定报告的 pytest-html ``data-jsonblob``，只收集其中 **Failed / Error**（不含 Skipped / xFailed）。过滤顺序：先 device / ``--priority``，再按报告 nodeid。报告无失败、或失败 nodeid 与当前 collection 全不匹配时退出码 2；部分匹配则跑匹配项并对未匹配打 warning。与 ``--lf`` 的区别：读指定 HTML，可跨机器复跑，不依赖本机 ``.pytest_cache``。

```python
@pytest.mark.P0
@pytest.mark.case_title(case_id="UI-01", title="role_a 登录成功进入 home")
def test_role_a_login(flow):
    ...
```

未安装对应包时静默跳过，不影响用例执行。

## 飞书通知（可选）

会话结束时向群机器人 Webhook 发送汇总。默认关闭；发送失败只打 warning，不改 pytest 退出码。

`config/env.yaml`：

```yaml
default:
  feishu:
    enabled: true
    webhook: https://example.com/hooks/bot  # 替换为你的群机器人 Webhook
    include_failures: false   # true 时附失败用例名
    failure_limit: 20
    timeout_sec: 5
```

## 在新产品仓库中使用

```bash
pip install pilot-framework   # 或 pip install -e /path/to/uiauto-Frame
pilot init path/to/your_product
```

`pilot init` 按框架约定**生成**产品仓骨架（pages / actions / checks / cases / flow / account / config），并附一条最小登录样例。可加 `--product NAME`（省略则用目标目录名）。目标目录已有文件时会拒绝写入；确认覆盖同名文件再加 `--force`。生成后必须：① 实现 `account/auth.py` 并已在 conftest 注册；② 复制 `config/env/lab.yaml.example` → `lab.yaml`；③ 补齐 Page 定位。

```bash
pilot init path/to/your_product
pilot init path/to/your_product --product myapp
```

查写用例约定（给 Agent；安装包内带有 `docs/to-agent`，不必打开框架仓库）：

```bash
pilot docs                  # 该读哪一篇
pilot docs show page        # 只输出这一篇
pilot docs search wait_ready
```

产品仓库需提供：

```
your_product/
  account/        # AuthProvider 实现（必做）
  pages/          # 页面对象（唯一接触 locator）
  actions/        # 业务 Actions（用例唯一 API）
  cases/          # 业务用例
  flow.py         # 组装 Flow
  config/
    product.yaml  # 共享默认 + 默认 env
    env/          # 每设备一份：lab-a.yaml（本地）+ *.yaml.example
  conftest.py     # 注册 AuthProvider + product flow
```

（兼容：仍可用单文件 `config/env.yaml`。）

用例示例：

```python
def test_submit_order(flow):
    flow.login_as("buyer")
    flow.order.create(sku="SKU-001", qty=2)
    flow.order.submit()
    flow.order.should_see_status("待支付")
```

## UI 用例数据驱动（可选）

适用：**同一 UI 流程**、不同输入/期望（表单校验、搜索词等）。浏览器贵、易抖，勿做成接口式组合矩阵；不同流程请拆成多条用例，不要硬塞进同一 YAML。

数据文件相对**用例 `.py`** 放置；每行必须有 `id` / `input` / `expect`，`id` 作 pytest node 名（截图/trace/报告可读）。

`cases/login/testdata/login.yaml`：

```yaml
- id: empty_password
  input:
    username: buyer
    password: ""
  expect:
    error_visible: true
    error_text: 请输入密码
- id: ok_login
  input:
    username: buyer
    password: secret
  expect:
    error_visible: false
```

`cases/login/test_login.py`：

```python
from pilot import cases

@cases("testdata/login.yaml")
def test_login(flow, case):
    flow.login(case.input.username, case.input.password)
    if case.expect.error_visible:
        flow.login.should_see_error(case.expect.error_text)
    else:
        flow.home.should_be_ready()
```

约定：用例层仍只编排 `flow.*`；禁止在用例里 `for` 多组数据（必须用 `@cases` 展开成独立 node）。设备过滤继续用 `@pytest.mark.device`，优先级用 `@pytest.mark.P0` 等，均不写入 YAML。

## 目录

- `src/pilot/` — 框架内核
- `tests/` — 框架单元测试
- `docs/to-agent/` — **Agent 编写 UI 用例入口**（`pilot docs`；或先读其中 `README.md`）
