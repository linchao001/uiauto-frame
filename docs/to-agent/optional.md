# 可选能力（短索引）

第一版写 UI 用例不必展开。需要时读下方指向；完整说明见仓库根 `README.md` 对应章节。

## `@cases` 数据驱动

- **何时**：同一 UI 流程、不同 input/expect（表单校验等）；勿做接口式组合矩阵
- **用法**：YAML 相对用例 `.py`；每行 `id` / `input` / `expect`；`@cases("testdata/xxx.yaml")` + `case` 参数
- **禁**：用例内 `for` 多组；设备/优先级不进 YAML
- 源码：`src/pilot/cases.py`；根 README「UI 用例数据驱动」

## DB

- 配置 `db`（+ 可选 `ssh` 自动开通远程）
- Fixture `db` 或 `get_db()`；断言 `BaseCheck.expect_row` 等；异步 `db.wait_*`（禁硬 sleep）
- 根 README「DB 落库」

## SSH

- 配置 `ssh`；fixture `ssh` / `get_ssh()`
- 根 README「SSH」

## 测试报告

- `pytest --env <name> --report` → `reports/<env>/<时间戳>/report.html`
- 开测前框架合并 ``AuthProvider.report_version_fields`` 到报告 Environment（未实现或失败只记日志）。产品钩子 ``pytest_pilot_report_metadata`` 可再追加字段，不要 ``clear()``
- 可选 `--report-dir`；仍可用手写 `--html=...`
- `--from-report PATH`：只重跑报告中 Failed/Error（PATH=`report.html` 或 run 目录）；不依赖 `--lf`
- `@pytest.mark.case_title` + P0–P3 → 报告 Case ID / Title / Priority；用例 `flow.step(...)` 写入报告步骤（Action 内 `report=False` 仅日志）
- 失败截图/trace 只在 ``--report`` 时落在 ``reports/<env>/<时间戳>/artifacts/``，报告内相对链接可点开；未开报告不生成
- 根 README「测试报告」

## 飞书通知

- `feishu.enabled` + webhook；会话结束汇总；失败不改 pytest 退出码
- 根 README「飞书通知」
