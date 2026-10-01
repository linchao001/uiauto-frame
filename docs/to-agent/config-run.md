# 用例仓库配置

改设备、对配置字段时读。对照：`pilot init` 生成的 `config/`。

## 文件

```text
config/
  product.yaml                 # 产品共享默认 + 默认设备名
  env/<device>.yaml.example    # 仓库内模板（可提交）
  env/<device>.yaml            # 本地真值：base_url / 账号 / ssh / db（gitignore）
```

设备名 = `env/` 下文件名（不含后缀），例如 `env/lab.yaml` → `lab`。`@pytest.mark.device("lab")` 用的就是这个名字。

首次使用：

```bash
cp config/env/lab.yaml.example config/env/lab.yaml
# 再编辑 lab.yaml 填入本机可达地址与口令
# 并实现 account/auth.py（AuthProvider）
```

加载顺序：代码默认 < `product.yaml` < `env/<name>.yaml` < CLI（`--env` 选设备；`--pilot-browser` / `--pilot-headed` 覆盖浏览器）。

选哪台设备：CLI `--env` > `product.yaml` 的 `env` > 目录里只有一个 env 文件时自动用它 > `local`。已有 env 文件时，解析出的名字必须在其中，否则报错。

仍兼容旧单文件 `config/env.yaml`（顶层 `default` + 命名设备块）。有 `product.yaml` 或 `env/` 时优先分层目录。

## 鉴权（产品必须实现）

框架**不**内置登录/建号 HTTP。产品仓须：

1. 实现 `account/auth.py` 中的 `AuthProvider` 子类（必做：`login` / `token_store_items`；可选：`recreate_test_account`、`report_version_fields`）
2. 在 `conftest.py` 的 `pytest_configure` 里 `register_auth_provider(config, ProductAuth())`

业务接口路径、请求体字段、表名等写在产品实现或产品自有配置里，框架不解析。

## product.yaml

只放各设备共享的默认，不要写某台机器的 `base_url` / 账号。

```yaml
product: demo
env: lab                      # 省略 --env 时的默认设备
default_account: test_user    # 可选；与 accounts 中的 key 对齐
browser:
  browser: chromium           # chromium | firefox | webkit
  headless: true
  timeout_ms: 15000
  viewport_width: 1920        # 可选；默认 1280
  viewport_height: 1080       # 可选；默认 720
```

`product` 只是标识，不参与加载。未写的浏览器字段用代码默认（视口 1280×720、导航超时 30s 等），见 `BrowserSettings`。

## env/<device>.yaml

覆盖同名字段。`browser.base_url`、账号、SSH、DB 放这里。**勿提交仓库**（见根目录 `.gitignore`）。

```yaml
browser:
  base_url: https://device.example

accounts:
  test_user:                  # 与 default_account / 角色映射对齐
    username: testuser
    password: "***"

ssh:                          # 可选；有 user 即启用。host 可省略
  user: sshuser
  password: "***"

db:                           # 可选；有 user 或 database 即启用。host 可省略
  port: 3306
  user: dbuser
  password: "***"
  database: app_db
```

会话开始框架会调用 `AuthProvider.recreate_test_account`（默认 no-op）。需要重建测试账号时在产品实现中覆盖。

省略的主机：`db.host` 回落 `base_url` 主机，再无则 `127.0.0.1`。`ssh.host` 回落已启用的 `db.host`，否则回落 `base_url` 主机。

`feishu` 可写在 `product.yaml` 或设备文件；缺省关闭。字段见 `optional.md`。
