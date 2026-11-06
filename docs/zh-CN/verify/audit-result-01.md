# 审计「结果」着色 01 · 验证记录

背景：审计页 / 概览页的「工具调用」结果展示，成功时是正文黑色，只有失败才标红；成功与失败
应当对称着色。本轮同时覆盖详情弹窗的「结果」卡片，以及概览页「最近的工具调用」表格的结果列。

## 变更

| 文件 | 改动 |
|---|---|
| `web/templates/audit.html` | 详情弹窗「结果」成功分支包 `<span class="audit-detail__ok">` |
| `web/templates/overview.html` | 详情弹窗同上；「最近的工具调用」表格「结果」列成功分支同样着色（失败分支原本就用 `audit-detail__error`） |
| `web/static/app.css` | 新增 `.audit-detail__ok { color: var(--success); }`；失败已有 `.audit-detail__error` → `var(--danger)` |

复用既有语义色 token，未新增颜色：浅色 `--success #15803d`、深色 `--success #3fb950`。

## 验证

- Chrome 156 headless 实测 computed color（真实 `app.css` + 对应结构）：
  - 浅色：成功 `rgb(21, 128, 61)`，失败 `rgb(180, 35, 24)`
  - 深色：成功 `rgb(63, 185, 80)`，失败 `rgb(248, 81, 73)`
- 截图：
  - 详情弹窗：[浅色](assets/ui/audit-result-light.png)、[深色](assets/ui/audit-result-dark.png)
  - 概览表格：[浅色](assets/ui/overview-result-light.png)、[深色](assets/ui/overview-result-dark.png)
- `pytest` 全量：525 passed, 1 failed（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）。
- `ruff check .`：全过。

## 边界

- 覆盖范围：审计详情弹窗、概览详情弹窗、概览「最近的工具调用」表格结果列；审计列表的结果列与结果筛选见 `audit-outcome-01.md`。
- 未知结果（`known` 为假且无错误）仍显示灰色「—」，不参与着色。
- 颜色全部来自既有 token，浅色/深色主题自动适配，不新增硬编码色值。
