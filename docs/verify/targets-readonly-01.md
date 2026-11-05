# 分析员只读目标页 01 · 验证记录

背景：分析员原本看不到目标清单（`/targets` 被服务端整体 403），但排查时又需要知道有哪些环境、
目标、端点、授权范围和最近测试状态。本轮新增「分析员只读目标页」：同一 `/targets` 按角色渲染，
分析员只能 GET 该页，不能进行任何写操作；管理页行为不变。

## 变更

| 层 | 改动 |
|---|---|
| 权限 | `web/security.py`：`_requires_admin(path, method)` 改为「方法 + 精确路径」放行，仅 `GET/HEAD /targets` 对分析员开放；`/targets/new`、`/targets/{id}/edit`、`/targets/{id}/delete` 及所有 `POST /targets*` 仍为管理员专属 |
| 路由 | `web/routes.py::_render_targets` 按角色分支：分析员渲染只读模板，只构造白名单字段（名称/类型/端点/授权范围/状态/最近测试/失败原因），不传管理动作数据 |
| 视图 | `web/views.py` 新增 `ScopeDetail` 与 `scope_details()`：按类型把 `allowed_dbs` / `allowed_indices` / `allowed_projects` / `allowed_vhosts` / `allowed_topics` / `key_prefix` 拆成「标签 + 具体值」，Redis 空前缀显示「不限」 |
| 模板 | 新增 `templates/targets_readonly.html`：无「管理环境」「新建目标」「新建环境」、无操作列、名称不链接编辑页；统计四张卡保留；停用环境/停用目标照常列出并标注；最近测试含失败详情（不含安装按钮） |
| 导航 | `base.html`：「排查」组对 both 角色显示「目标」，仅管理员显示「环境」 |
| 样式 | 新增只读表授权范围列宽与 `scope-line` / `scope-chip` 样式；CSS 预算从 54KB 调到 55KB（本次新增约 430B，当前 54.4KB） |
| 文案 | 新增 12 条中文文案的英文翻译（只读说明、停用提示、空状态、各授权范围标签、「不限」） |

## 可见性矩阵（分析员）

| 内容 | 可见 | 说明 |
|---|---|---|
| 环境卡片（展示名 / key / 目标数 / 停用标记） | ✅ | 调用工具要传 environment |
| 名称、类型、启用状态 | ✅ | 调用工具必填参数 |
| 端点（host:port/db 等） | ✅ | 按需求放开 |
| 授权范围（具体库/索引/vhost/topic/key 前缀） | ✅ | 按需求放开，细粒度列出 |
| 最近测试（成功/失败 + 时间）与失败原因 | ✅ | 与 MCP `systems_status` 的信息集一致 |
| 统计四张卡（含密钥异常数量） | ✅ | 按需求保留；不提供修复入口 |
| 新建 / 编辑 / 删除 / 启停 / 测试 / 安装客户端 / 管理环境 | ❌ | 服务端 403，页面也不渲染 |

## 验证

- 角色测试（`tests/test_roles.py`）扩展：
  - 分析员 `GET /targets` → 200；页面含目标名、端点 `10.1.1.1`、细粒度授权范围 `live` / `logs`、只读说明；不含 `管理环境` / `新建目标` / `新建环境` / `编辑` / `删除目标` / `安装客户端` / `data-row-action` / `/targets/new` 等链接
  - 停用环境：`GET /targets?env=legacy` → 200，显示停用环境告警、停用目标与端点
  - 权限矩阵：分析员 `GET /targets/new`、`/targets/{id}/edit`、`/targets/{id}/delete`、`/settings`、`/users`、`/environments` → 403；`POST /targets`、`/targets/{id}/toggle|test|delete|install-client` → 403；JSON 请求返回 `FORBIDDEN`
  - 管理员导航仍显示「环境」，分析员导航只有「目标」
- 全量 `pytest`：528 passed, 1 failed（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）。
- `ruff check .`：全过。
- 真实页面截图（测试客户端以分析员登录渲染 `/targets`，Chrome 156 截图）：
  - [默认环境](assets/ui/targets-readonly-1440.png)
  - [停用环境](assets/ui/targets-readonly-legacy-1440.png)
  - [390 堆叠](assets/ui/targets-readonly-390.png)
  - [深色](assets/ui/targets-readonly-dark-1440.png)
- 新模板 `t()` 文案已全部有英文翻译（脚本校验无缺失）。

## 安全与边界

- 只放行精确路径 `GET /targets`，不是前缀放行；分析员直接请求其他管理 URL 仍 403，页面隐藏不承担安全职责。
- 分析员页面不渲染任何写操作控件；密钥从不进入页面数据（与管理员页一致）。
- 分析员能看到所有环境与目标（含停用），与 MCP `systems_status` 的能力对齐；停用项明确标注「已停用」。
- 「密钥异常」只显示统计数量，不提供录入/修复入口（管理员才有）。
- 失败原因展示的是已脱敏的 `last_test_error`，与 MCP 返回一致。
- 未做「按分析员限制环境/目标可见范围」的白名单；当前模型下分析员可查询所有已启用环境，如未来要按人隔离需要另立方案。
