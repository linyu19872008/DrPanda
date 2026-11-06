# 工具错误治理 P0 01 · 验证记录

背景：SQLite 审计里 292 次工具调用有 32 次失败（11%），分析后确认只有两类需要改代码：
`mysql_explain` 被模型传 `EXPLAIN ...` 时内部又拼一次导致 `EXPLAIN EXPLAIN` 被拒；以及审计只存
错误码、不存错误消息，导致 10 条 `UPSTREAM_UNAVAILABLE` 无法归因。本轮修这两项。

## 变更

### 1. `mysql_explain` 容忍 EXPLAIN 前缀

| 层 | 改动 |
|---|---|
| 工具 | `tools/data.py`：新增 `_explain_inner()`，入参自带 `EXPLAIN` 时先去掉，内部只拼一次；docstring 写明「可带或不带 EXPLAIN 前缀，不支持 EXPLAIN ANALYZE」 |
| 测试 | `tests/test_tools_data.py`：`mysql_explain` 追加传入 `EXPLAIN SELECT ...` 的用例，断言实际执行语句是单层 `EXPLAIN SELECT ...` |

复现依据：`guard.check_sql("EXPLAIN EXPLAIN SELECT ...")` → `GUARD_REJECTED / mysql.explain_target`；
`guard.check_sql("EXPLAIN SELECT ...")` → 放行。改动后同样输入会走单层 EXPLAIN。

### 2. 审计记录脱敏错误详情

| 层 | 改动 |
|---|---|
| 模型 | `store/models.py`：`audit.error_detail`（String(512)，nullable） |
| 迁移 | `0011_audit_error_detail.py`：新增列；旧行保持 NULL，无需回填 |
| 协议/仓储 | `AuditEntry` / `AuditRecord` 增加 `error_detail`；append 时截断 512，list 时读回 |
| 写入 | `tools/base.py::write_tool_audit`：失败时把 `error_message` 用目标密钥 `redact` 后截断 512 写入 |
| 展示 | `audit.html`、`admin_overview.html`：失败结果卡片在「CODE（中文标签）」下方显示一行脱敏错误消息；新增 `.audit-detail__error-note` 样式 |

## 验证

- `tests/test_tools_data.py`：EXPLAIN 前缀用例通过（单层 EXPLAIN）。
- `tests/test_logging.py`：失败调用落 `error_detail`，超长消息截断为 512。
- `tests/test_store_contract.py`：`error_detail` 落库与读回一致。
- `tests/test_migrate.py`：升级模拟路径同时回退 `error_detail` 列，0003→HEAD 可正常升级；新建库校验列存在。
- `tests/test_audit_page.py`：失败详情在审计弹层 HTML 中渲染。
- 迁移在**真实数据副本**上验证：升级到 `0011_audit_error_detail`，`audit` 列齐全，历史行 `error_detail` 全为 NULL。
- 全量 `pytest`：532 passed, 1 failed（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）；`ruff check .` 全过。
- 截图（测试客户端渲染审计弹层，Chrome 156）：
  - [失败卡片：错误码 + 脱敏错误详情](assets/ui/audit-error-detail-1440.webp)

## 边界

- 只有 `tool.call` 失败写 `error_detail`；`target.test` 失败原因本来就在 `summary` 里，不重复存。
- 旧审计行不回填；弹层对 NULL 不展示该行。
- 错误消息按目标密钥脱敏并截断 512 字符，避免把连接串、密码等写进审计；内部异常的消息也会写入（脱敏为尽力而为）。
- 列表摘要预览、MCP 工具返回的 `CODE: message` 契约不变。
- 本轮只做 P0；P1（SCOPE_DENIED 带允许列表、`systems_status` 返回 scope、提示词引导）与 P2 未做。
- 迁移在服务启动时自动执行并自动备份，**需要重启服务生效**。
