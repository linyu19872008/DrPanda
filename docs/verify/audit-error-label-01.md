# 审计错误码中文化 01 · 验证记录

背景：中文界面里，审计详情弹层的「结果」卡片只显示原始错误码（如 `UPSTREAM_UNAVAILABLE`）。
本轮按确认的方案在码后补中文标签，显示为 `UPSTREAM_UNAVAILABLE（上游不可用）`；英文界面用
半角括号 `UPSTREAM_UNAVAILABLE (upstream unavailable)`。列表「摘要」预览保持原始码不变。

## 变更

| 层 | 改动 |
|---|---|
| 展示字典 | 新增 `web/labels.py`：`ERROR_LABELS`（17 个错误码 → 中文短标签）与 `error_label()`（未知码回退原码）；`ERROR_CODE_DISPLAY = "{code}（{label}）"` |
| 渲染 | `web/render.py` 向模板注入 `error_label` 与 `ERROR_CODE_DISPLAY` |
| 模板 | 审计详情弹窗、概览详情弹窗、概览「最近的工具调用」结果列：错误码改为 `t(ERROR_CODE_DISPLAY, code=..., label=t(error_label(...)))` |
| 文案 | `en.json` 新增 17 条标签英文（如「上游不可用」→ upstream unavailable）和展示模板（半角括号） |
| 文档 | `ui-design.md` 5.8 补充错误码展示规则 |

未改动：MCP 工具返回的 `CODE: message` 契约、审计数据（仍只存错误码）、列表摘要预览文本。

## 验证

- 新增 `tests/test_labels.py`：
  - `ERROR_LABELS` 必须覆盖 `errors.ALL_CODES`（防止以后新增错误码漏配）
  - 未知码回退原码
- `tests/test_audit_page.py`：中文页面断言 `UPSTREAM_UNAVAILABLE（上游不可用）`，英文页面断言 `UPSTREAM_UNAVAILABLE (upstream unavailable)`。
- 全量 `pytest`：528 passed, 1 failed（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）。
- `ruff check .`：全过。
- 截图（测试客户端渲染 `/audit` 并打开失败详情，Chrome 156）：
  - [失败结果卡片：CODE（中文标签）](assets/ui/audit-error-label-1440.png)

## 边界

- 只能中文化「错误类别」，不能显示具体原因：审计 summary 只记录 `error=<CODE>`；详细错误原文在进程日志，用弹层的「请求号」关联。若要在弹层直接看原因，需在审计写入时记录脱敏后的错误摘要（另一项改造）。
- 历史审计记录在渲染时映射，无需数据迁移。
- 列表摘要预览仍保留原始码（按确认不做中文化）。
- 该映射只影响网页显示；模型通过 MCP 拿到的仍是 `CODE: message`。
