# 审计结果列 + 结果筛选 01 · 验证记录

背景：审计列表只有「查看」弹层里能看到成败，失败信息容易漏看。本轮按方案 A + P1 落地：
新增「结果」列（放在摘要之前），并把结果结构化落库，支持「全部/成功/失败」筛选。

## 变更

| 层 | 改动 |
|---|---|
| 存储 | `audit` 新增 `outcome` 列（`ok` / `failed` / NULL）；`AuditEntry` / `AuditRecord` 增加 `outcome`；`ConfigStore.list_audit` 支持 `outcome` 过滤 |
| 迁移 | `0010_audit_outcome`：加列 + 按 summary 回填旧行（`tool.call` 的 `error=-` / `error=<code>`；`target.test` 的 `ok` / `failed: ...`），其余动作为 NULL |
| 写入 | `tool.call` 按 `error_code` 落 `ok`/`failed`；`target.test` 按测试结果落；其余动作不写 |
| 展示 | 审计表新增「结果」列（摘要之前，定宽 76px）：成功绿、失败红（悬停显示错误原因），无成败语义显示灰色破折号；失败位只显示「失败」两字，不用长错误码撑宽列 |
| 筛选 | 筛选栏新增「全部结果 / 成功 / 失败」下拉，与动作、环境、对象名一起生效；`清除筛选` 一并重置 |
| 兼容 | `_TOOL_SUMMARY` 的 `env=` 改为可选，48 条早期无 `env=` 的工具审计也能显示结果；列表在 `outcome` 为空时按 summary 兜底解析 |
| 样式 | 审计表 `.cell-result` 定宽 76px、`.cell-fill` 最小宽 12rem→10rem，保证 1121–1300 视口 8 列不裁切 |
| 文案 | 新增「全部结果」及对应英文翻译；「结果」「成功」「失败」复用既有文案 |

## 验证

- 新增测试：
  - `test_audit_outcome_backfilled_on_upgrade`：模拟 0009 → 0010，断言 5 类历史行回填为 `ok/failed/ok/failed/NULL`
  - `test_audit_outcome_persisted_and_filterable`：写入与 `list_audit(outcome=...)` 过滤、原始行落库
  - `test_audit_page_shows_result_column_and_filters_by_outcome`：结果列渲染（成功/失败/破折号、失败 title）、`outcome=` 筛选、失败与无结果动作的排除
- 全量 `pytest`：528 passed, 1 failed（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）。
- `ruff check .`：全过。
- 真实页面截图（测试客户端渲染 `/audit`，Chrome 156 截图）：
  - [1440 列表](assets/ui/audit-outcome-1440.png)
  - [仅失败筛选](assets/ui/audit-outcome-failed-1440.png)
  - [深色主题](assets/ui/audit-outcome-dark-1440.png)
  - [390 堆叠](assets/ui/audit-outcome-390.png)

## 迁移与上线

- 启动时自动迁移（迁移前自动备份 SQLite，见 `backup_keep_count`）；**需要重启服务**才会执行 `0010` 并回填历史行。
- 回填规则是纯字符串解析，覆盖现有 `tool.call` / `target.test` 历史；解析不到的行保持 NULL（显示按摘要兜底，但不参与结果筛选）。
- 分析员视图默认动作仍是工具调用，结果筛选同样可用。

## 边界

- 结果筛选只对 `outcome` 非空的行生效；新建/修改/删除/Token/设置等动作没有成败语义，选中成功或失败时不会出现。
- 结果列只显示「成功 / 失败」，具体错误码/原因看悬停或「查看」弹层。
- 摘要列仍是 2 行截断；失败错误码可能被截断，但结果列已独立呈现成败，不依赖摘要文本。
- 概览页「最近的工具调用」表格与详情弹层此前已加结果着色（见 `audit-result-01.md`），本轮未改动。
