# 概览页加环境列 01 · 验证记录

背景：概览页的两张「最近调用」表都只有时间、目标名、工具名、结果，无法直接看出这次调用属于
哪个环境；审计列表和目标列表已有环境列。本轮给个人概览「最近的工具调用」与管理概览「最近操作」
都补上环境列。

## 变更

| 层 | 改动 |
|---|---|
| 数据 | `web/overview.py::_personal_overview`：从环境列表取展示名，给每条调用补 `environment_key` / `environment_title` |
| 模板 | `overview.html` 的最近调用表在「时间」后新增「环境」列；`admin_overview.html` 的「最近操作」表在「动作」后新增环境列。默认环境显示「默认」，其它显示展示名 + 调用标识（第二行等宽小字），无环境显示破折号 |
| 样式 | `.table--audit .cell-key` 改为通用 `.cell-key`，让概览表的调用标识第二行复用同一套弱化样式（CSS 总量不变） |
| 测试 | `tests/test_roles.py`：分析员个人概览出现 `环境` 表头、「默认」与目标名；管理员管理概览的「最近操作」出现 `环境` 表头 |

## 验证

- 角色测试：分析员个人概览断言 `>环境</th>`、`默认`、目标名同时出现。
- 全量 `pytest`：530 passed, 1 failed（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）。
- `ruff check .`：全过。
- 截图（测试客户端渲染个人概览，Chrome 156）：
  - 个人概览：[环境列：默认 / 畅聊生产](assets/ui/overview-personal-env-column-1440.png)
  - 管理概览：[最近操作环境列](assets/ui/overview-admin-env-column-1440.png)

## 边界

- 环境展示格式与审计列表、目标列表一致：展示名 + 调用标识两行；行高会随第二行略增。
- 审计记录保留的是 `environment_key`；环境已删除时按 key 回退显示，环境为空显示破折号。
- 两张表都加了环境列：个人概览「最近的工具调用」、管理概览「最近操作」。
- 不改变数据库、审计数据和 MCP 工具输出。
