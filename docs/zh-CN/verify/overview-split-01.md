# 概览页角色拆分 01 · 验证记录

背景：`/` 之前按角色渲染两套互斥内容——管理员看全局健康，分析员看个人概览，导致管理员看不到
「可查询的目标 / 我的 Token / 我的调用」。本轮把 `/` 统一为个人概览（管理员是分析员的超集），
管理员专属的全局健康拆到独立页面 `/admin/overview`（管理概览）。

## 变更

| 层 | 改动 |
|---|---|
| 路由 | `web/overview.py`：`/` 只构建个人概览（所有角色）；新增 `GET /admin/overview` 渲染管理概览；`_admin_signals()` 给管理员提供入口计数 |
| 权限 | `web/security.py`：`_ADMIN_PREFIXES` 增加 `"/admin"`；分析员访问 `/admin/overview` 返回 403 |
| 导航 | `base.html`：管理员在「概览」下新增顶层「管理概览」；`render.py` 的 `nav_active` 增加 `/admin` → `admin` |
| 模板 | `overview.html` 重写为个人概览（页头给管理员「管理概览」按钮 +「N 个目标需要处理」计数徽标）；新增 `admin_overview.html`（四个全局数字、需要处理、最近操作 + 详情弹层） |
| 文案 | `en.json` 新增「管理概览」「{count} 个目标需要处理」 |
| 文档 | `ui-design.md` 5.1 拆成「概览」+「管理概览」；`planning.md` 路由表与角色说明更新 |

登录落地不变：所有人仍落 `/`；管理员从个人概览点「管理概览」进入全局页。

## 验证

- `tests/test_roles.py`：
  - 管理员 `/` 显示个人概览（可查询的目标、最近的工具调用、`1 个目标需要处理` 徽标、`href="/admin/overview"`），不再显示「最近操作」；
  - 管理员 `/admin/overview` 200，显示「管理概览」标题、需要处理（名称链到 `/targets/{id}/edit`）与最近操作；
  - 分析员 `/` 不变，且不含「管理概览」；`GET /admin/overview` → 403 并带「没有权限」。
- `tests/test_web.py`：导航顺序断言更新为「概览 < 管理概览 < 目标 < 环境 < 审计」；个人概览出现入口链接，空态「没有需要处理的目标」迁到管理概览。
- 全量 `pytest`：530 passed, 1 failed（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）；`ruff check .` 全过。
- 真实页面截图（测试客户端渲染，Chrome 156）：
  - [管理员个人概览（含入口与计数徽标）](assets/ui/overview-personal-1440.png)
  - [管理概览](assets/ui/overview-admin-1440.png)
  - [分析员个人概览（无管理入口）](assets/ui/overview-analyst-1440.png)
  - [个人概览 390](assets/ui/overview-personal-390.png)

## 边界与说明

- 管理概览保留「最近操作」详情弹层与「查看全部」；「需要处理」名称链到目标编辑页，仅管理员页有该链接。
- 个人概览的计数徽标按「有问题的目标数」去重（失败或密钥异常按目标计一次），不做明细。
- `/` 的 URL 与登录落地不变；新增页面不影响既有书签。
- 数据查询层面，管理员打开 `/` 会多一次目标列表统计（用于入口徽标），开销可忽略。
- 未改变数据库结构、MCP 工具和审计数据。
