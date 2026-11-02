# 系统配置页分组与扩展

## 变更

新增 4 个系统配置键（`settings` 表仍为 key/value，无 schema 变更）：

| 分组 | 键 | 默认 | 范围 | 生效 |
|---|---|---:|---|---|
| 新建目标默认值 | `default_target_timeout_s` | 15 | 1–120 | 新建目标表单 |
| 新建目标默认值 | `default_target_max_rows` | 100 | 1–1000 | 新建目标表单 |
| 新建目标默认值 | `default_target_max_bytes` | 102400 | 4096–1048576 | 新建目标表单 |
| 并发与审计 | `audit_cleanup_interval_minutes` | 60 | 5–1440 | 下一轮清理 |
| 高级资源 | `catalog_max_clients` | 32 | 4–128 | 下一次工具调用 |

现有 `target_max_concurrency`、`audit_retention_days` 保留。

页面：

- 左侧子菜单切换分组：可编辑的“新建目标默认值”“并发与审计”“高级资源”，以及只读的“安全边界”“启动配置”“最近变更”；
- 每次只渲染当前分组；保存按钮只提交当前分组，URL 使用 `?section=<key>`；
- 启动配置展示 host/port/DB 类型/日志级别/密钥来源，不显示密钥；
- 每项显示默认值、范围、生效标签；
- 字段级错误、顶部错误摘要锚点、`aria-invalid`/`aria-describedby`；
- 保存失败保留用户输入；
- 保存后 `?flash=saved`。
- 提供“恢复默认值”确认页（`/settings/reset`）；支持全局恢复和单项恢复（`?key=<key>`），均写审计。
- “最近变更”侧栏展示最近 5 条 `settings.update` 审计摘要。

新建目标表单读取全局默认值；既有 target 的 `timeout_s` / `max_rows` / `max_bytes` 不受影响。

## 验证

- `pytest`：**410 passed**（新增配置、分组、新目标默认值、字段错误、单项/全局 reset、history、catalog 缓存上限、子菜单切换用例）
- `ruff check .`：通过
- 未启动真实浏览器截图；分组与可访问性由模板/测试断言覆盖

## 未纳入

- `catalog_max_clients`、`DR_PANDA_HOST/PORT/DATABASE_URL/LOG_LEVEL/SECRET_KEY` 仍为启动/环境配置，不做网页可写项。
- 安全硬边界（只读白名单、危险命令、行/字节上限、ES 窗口等）不通过系统配置放宽。
- 真实浏览器视觉/键盘验收仍待补。
