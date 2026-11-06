# 审计参数 limit 统一展示 01 · 验证记录

背景：审计详情弹层里，MySQL 工具的行数上限是 SQL 下方单独一行「最多 N 行」，而 Mongo/ES
等工具的 `limit` 显示在「参数」键值列表里（`limit: 20`），同一类信息两种呈现。本轮把 MySQL
也对齐为普通参数项。

## 变更

| 层 | 改动 |
|---|---|
| 解析 | `web/audit_page.py`：删除 `_describe_params` 里「有 SQL 时的 limit 特判」和 `_limit_text`，`limit` 与其它参数一样进入 `params_fields`；`params_limit` 字段移除 |
| 模板 | `templates/_audit_params.html`：删除 SQL 下方「最多 {n} 行」行；`has_params`、隐藏复制块里的 `params_limit` 分支一并移除 |
| 样式 | `app.css`：删除 `.audit-detail__limit` 两条规则与组合选择器（CSS 总量 54.4KB → 54.3KB） |
| 文案 | `en.json`：删除不再使用的「最多 {n} 行」翻译键 |
| 文档 | `ui-design.md` 5.8：改为「`limit` 和其它参数一样按名字和值列出」 |
| 测试 | `test_audit_page.py`（页面/复制/英文断言、4 处单测）、`test_logging.py`、`test_masking.py` 改为断言 `params_fields` 含 `("limit", "N")`、复制内容含 `limit: N` |

## 行为

- 弹层「参数」区：SQL 代码块之后，按参数名与值列出 `limit: 20`，与 Mongo/ES 一致；不再出现「最多 20 行」。
- 「复制」内容：`<SQL>\nlimit: 20`。
- 英文界面同样显示 `limit: 20`（参数名不翻译），不再出现「Up to 20 rows」。
- 「返回条数」卡片不变，仍是实际返回条数。

## 验证

- 单测/页面测试：27 passed（`test_audit_page.py`、`test_logging.py`、`test_masking.py`）。
- 全量 `pytest`：528 passed, 1 failed（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）。
- `ruff check .`：全过。
- 截图（测试客户端渲染 `/audit` 并打开详情弹层，Chrome 156）：
  - [SQL + limit 参数项](assets/ui/audit-limit-param-1440.webp)

## 边界

- 旧审计记录在渲染时重新解析，**不需要数据迁移**；历史行的显示方式与新行一致。
- 显示值是**调用方请求的 `limit`**（`params={"sql": ..., "limit": ...}`），不是服务端 `clamp_limit` 后的生效上限；Mongo/ES 记录的同样是请求值，因此展示口径现在一致。若以后要显示生效上限，需要在工具写入审计时额外记录（另一个改动）。
- MCP 工具返回值与数据库字段不变，只影响网页弹层与复制内容。
