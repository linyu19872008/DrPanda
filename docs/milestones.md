# Dr Panda MCP 任务里程碑

> 把 [planning.md](planning.md)（v0.4）的方案拆成可独立验证的检查点。每个里程碑都给出目标、前置、任务、交付物、验证目标与退出条件。
>
> 本文只拆任务与验证，不含排期、时间、人力估算。契约以 planning.md 为准；本文与契约冲突时先改 planning.md，再改本文。

## 文档信息

| 项 | 值 |
|---|---|
| 版本 | v0.2 |
| 依据 | `docs/planning.md` v0.4 |
| 状态 | 未开始 |
| 用途 | 开发顺序、验收口径、进度跟踪 |
| 不含 | 排期、时间、人力、成本 |

## 1. 怎么用

- 里程碑是**可独立验证的检查点**。M0–M7 按序推进；前一个里程碑没有通过退出条件，不进入下一个。
- 每个里程碑的内容固定为：目标、前置、任务清单、交付物、验证目标、退出条件、注意点。
- 任务编号 `Mx.y`。完成一个勾掉一个；任务做完不等于里程碑完成，**验证目标全部通过、退出条件全部满足**才算完成。
- 验证目标写成"验证项 / 方法 / 通过标准"，方法是可执行的命令、接口调用或页面操作，不接受"看起来对"。
- 契约变更流程：先改 `planning.md` → 再调整本文任务与验证项 → 最后改代码。
- 状态跟踪表见第 8 章；每个里程碑收口时同时更新本文件状态。

## 2. 里程碑总览

| 编号 | 里程碑 | 对应规划分期 | 一句话目标 | 前置 |
|---|---|---|---|---|
| M0 | 工程地基 | 第一期 | 仓库能启动、依赖齐全、错误码与测试骨架就位 | — |
| M1 | 配置库与系统配置 | 第一期 | targets / audit / settings 可读写，密钥加密，契约测试全绿 | M0 |
| M2 | 闸门与最小只读连接 | 第一期 | 八类目标都有"最小只读"实现，白名单与危险清单生效，拒绝无外呼 | M1 |
| M3 | 配置台网页与 MCP 接入 | 第一期 | 网页可管目标与系统配置，三个客户端能连上并看到 `systems_status` | M2 |
| M3.5 | 配置台视觉与主题重构 | 第一期补强 | 设计系统、明暗主题、页面重构，仍为零 JS | M3 |
| M4 | 日志到代码 | 第二期 | CLS 与 GitLab 五个工具加 `investigate_error` 可用 | M3.5 |
| M5 | 数据面 | 第三期 | MySQL / Mongo / ES / Redis 十七个工具可用，含 schema 发现 | M4 |
| M6 | 消息面 | 第四期 | RabbitMQ 与 Kafka 五个工具可用 | M5 |
| M7 | 登录 | 第五期 | 网页与 `/mcp` 加同一套身份验证，审计记到人 | M6 |

里程碑与工具数量的对应：

| 里程碑结束时 | 可见工具 |
|---|---|
| M3 | 1 个（`systems_status`） |
| M4 | 6 个（第一批全部） |
| M5 | 23 个（前三批数据面加完） |
| M6 | 28 个（全部工具） |

工具批次与里程碑的对应：第一批 = M3 的 `systems_status` + M4 的五个；第二批 = M5 的十七个；第三批 = M6 的五个。

## 3. 全局约束（每个里程碑都要满足）

这些不是某个里程碑的任务，而是每次收口的隐含验证项。任何一项被破坏，里程碑不能算完成。

| # | 约束 | 验证方式 |
|---|---|---|
| G1 | 绝对只读：没有写操作工具，闸门在建立连接之前 | 工具清单审查；拒绝用例断言连接 0 次 |
| G2 | 危险与高开销规则（planning 6.6）对所有新组件生效 | 每个新增组件至少一条管理类、一条高开销拒绝用例 |
| G3 | 密钥不落明文：页面、日志、审计、工具返回、错误信息 | grep 原始行与日志；密文信封检查 |
| G4 | 每次调用有界：超时、行数、字节、并发（`target_max_concurrency`） | 上限用例（构造大结果、超时、并发排队） |
| G5 | 审计可追溯且不含密钥；配置变更与审计同事务 | 审计行检查；回滚用例 |
| G6 | 契约稳定：工具名、参数名、返回包络（planning 8.1/8.9）不变 | 内存客户端测试断言工具名与包络键 |
| G7 | 不缓存目标配置，网页改动立即生效 | 改配置后下一次调用行为变化 |
| G8 | 测试不连真实线上系统、不用真实凭证 | 测试夹具审查；拒绝路径无外呼 |
| G9 | 系统配置只能调整运行策略，不能放宽只读、危险规则、密钥、范围 | 设置页键白名单用例 |
| G10 | 文档同步：契约变更改 `planning.md`，使用方式变更改 README | 收口检查 |

## 4. 全局验证基线

所有里程碑共用这些命令与环境，不重复解释：

```
uv sync                          # 默认依赖。补单个 extra 加 --inexact；一次装齐用 uv sync --all-extras
uv run pytest -q                 # 全部测试
uv run python scripts/smoke.py   # 冒烟：启动 → healthz → （M3 起）MCP 客户端调工具
uv run dr-panda-mcp              # 启动服务，默认 127.0.0.1:8111
```

- 测试环境一律用临时 SQLite 与临时密钥，不读用户真实的 `data/`、`secret.key`、`DR_PANDA_SECRET_KEY`。
- 每条验证项在收口时留一条可复现记录（命令、输出摘要或页面截图）。
- 命令失败即该项失败，不允许"重跑一次就过"当通过；恢复后要给出失败原因。

## 5. 里程碑详情

### M0 工程地基

**目标**：仓库从 `uv init` 脚手架变成能启动、能测试、有错误码与目录约定的空服务，后续里程碑不再返工基础设施。

**前置**：无。

**任务**

- [x] M0.1 `pyproject.toml`：依赖与 extras（`fastmcp`、`sqlalchemy[asyncio]`、`alembic`、`jinja2`、`uvicorn`、`aiosqlite`、`cryptography`、`sqlglot`；`[mysql]`/`[postgres]`；dev 组 `pytest`/`pytest-asyncio`/`httpx`/`ruff`；`pytest` 配置 `asyncio_mode="auto"`）；改写 `description`（对应 planning 11.1–11.3）。
- [x] M0.2 `.gitignore` 补 `data/`（含 `data/backup/`、`data/secret.key`）；README 骨架（定位、启动、环境变量、三个客户端配置、八类目标登记要点、只读与危险规则声明、测试命令）（11.4）。
- [x] M0.3 `config.py`：读 3.3 的五个环境变量并校验（含 `DR_PANDA_SECRET_KEY`）；`DR_PANDA_DATABASE_URL` 补异步驱动，缺驱动时报"安装哪组 extras"；`errors.py`：错误码常量收齐（`TARGET_*`、`INVALID_ARGUMENT`、`GUARD_REJECTED`、`DANGEROUS_OPERATION`、`SCOPE_DENIED`、`UPSTREAM_*`、`STORAGE_UNAVAILABLE`、`SECRET_UNAVAILABLE`、`INTERNAL`）（3.2/3.3/8.2）。
- [x] M0.4 最小应用：FastMCP 实例 + `http_app(path="/mcp")` + `/healthz` + Host/Origin 校验，监听 `DR_PANDA_HOST:DR_PANDA_PORT`；端口占用退出并提示（3.1/3.5/9.2）。此时 `/healthz` 只报进程存活，`db` 字段在 M1 接上。
- [x] M0.5 测试骨架：`tests/conftest.py`（临时 SQLite、临时密钥、FastMCP 内存客户端夹具）、`/healthz` 与配置校验的用例（12.1）。
- [x] M0.6 `scripts/smoke.py`：启动进程、探 `/healthz`、退出码正确；M3 起扩展为连 `/mcp` 调工具（12.1）。

**交付物**：可启动的最小服务、依赖与目录骨架、错误码表、测试与冒烟脚本骨架。

**验证目标**

| 编号 | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| V0.1 | 依赖声明可解析 | `uv sync` | 无错误，`uv.lock` 更新 |
| V0.2 | 冷启动 | `uv run dr-panda-mcp` + `curl -fsS http://127.0.0.1:8111/healthz` | 200，JSON 含 `ok` 与版本 |
| V0.3 | 端口可配 | 改 `DR_PANDA_PORT` 启动并访问 | 监听端口跟随；旧端口不可达 |
| V0.4 | 缺驱动报错 | `DR_PANDA_DATABASE_URL=mysql://...` 且未装 `[mysql]` | 启动失败，提示安装 `[mysql]` |
| V0.5 | 端口占用 | 先占端口再启动 | 非 0 退出，提示改 `DR_PANDA_PORT` |
| V0.6 | Host/Origin 防护 | 伪造 `Host` / 跨站 `Origin` 请求 | 分别 421 / 403 |
| V0.7 | 测试骨架可跑 | `uv run pytest -q` | 通过 |
| V0.8 | README 完整 | 人工核对 | 覆盖 11.4 全部条目 |
| V0.9 | 冒烟脚本 | `uv run python scripts/smoke.py` | 退出码 0 |

**退出条件**：V0.1–V0.9 全过；仓库无脚手架占位文案（`Hello from`、`Add your description here`）残留。

**注意**：M0 不实现任何配置库逻辑；`/healthz` 的 `db` 字段留到 M1，避免为了健康检查提前引入空实现。

---

### M1 配置库与系统配置

**目标**：`ConfigStore` 契约全部可执行，密钥加密落盘，系统配置（保留期、并发）默认值与校验就绪，SQLite 契约测试全绿。

**前置**：M0。

**任务**

- [x] M1.1 `store/url.py` 与引擎创建：URL 解析、异步驱动补全、SQLite 打开 WAL/外键/`busy_timeout`（5.1/5.6）。
- [x] M1.2 `store/models.py`：`targets`、`audit`、`settings` 三张表，列类型与索引按 5.3。
- [x] M1.3 Alembic 单链 + 启动迁移 + SQLite 迁移前备份（保留 5 份）+ `settings` 默认行幂等初始化（5.5）。
- [x] M1.4 `crypto.py`：密钥加载（`DR_PANDA_SECRET_KEY` 优先，否则 `data/secret.key`，缺失且无密文时生成 0600）、AES-256-GCM、按字段密文信封、AAD 绑定 target 名与字段名、`kid`（5.8）。
- [x] M1.5 `settings.py`：两个键的默认值（90、10）、键白名单、范围校验（1–3650、1–50）、读取时缺键补默认、非法值回退默认并记 WARNING（4.5/5.2/9.5）。
- [x] M1.6 `store/repository.py`：目标 CRUD、启停、测试结果、密钥补丁（set/clear/留空）、`settings` 更新、配置变更与审计同事务（5.2/5.4）。
- [x] M1.7 启动序列接入密钥校验：库里有密文但解不开时启动失败并提示恢复备份（3.2/9.5）。
- [x] M1.8 契约测试：planning 5.7 全部条目 + 系统配置四条（默认值、校验、同事务、白名单）（5.7）。
- [x] M1.9 `/healthz` 补 `db` 字段：配置库 `SELECT 1` 成功返回 ok，失败 503（9.2）。

**交付物**：`store/` 全套、`crypto.py`、`settings.py`、迁移脚本、契约测试。

**验证目标**

| 编号 | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| V1.1 | 契约测试 | `uv run pytest -q tests/test_store_contract.py` | 全绿 |
| V1.2 | 迁移幂等 | 连续启动两次 | 第二次无错误；用户改过的 `settings` 值不被重置 |
| V1.3 | 密文落盘 | 建目标后 `sqlite3 data/dr-panda.sqlite "select secret_json from targets"`，对明文做 grep | 不含任何明文；含 `v`/`kid`/`nonce`/`ct` |
| V1.4 | AAD 绑定 | 测试脚本把 A 目标密文换到 B 目标同名字段 | 解密失败 `SECRET_UNAVAILABLE` |
| V1.5 | 错密钥启动 | 换一个 `DR_PANDA_SECRET_KEY` 启动 | 非 0 退出，提示恢复 `secret.key` 或环境变量备份 |
| V1.6 | 默认值 | 空库读 `get_settings` | `90` 与 `10` |
| V1.7 | 非法配置 | 提交 `0`、`3651`、`51`、`abc` | 全部拒绝，库中值不变 |
| V1.8 | 同事务 | 模拟审计写失败 | 目标变更回滚，不留半条数据 |
| V1.9 | 健康检查 | `curl -fsS /healthz` | 200，`db` 为 ok |
| V1.10 | 名称与停用语义 | 重复名、停用目标读取 | 重复名拒绝；停用后读得到但 `enabled=false` |

**退出条件**：V1.1–V1.10 全过；`secret_json` 原始行无明文；迁移连续两次启动幂等。

**注意**：M1 不实现网页与工具；所有验证通过测试代码或临时脚本驱动仓储，不依赖 HTTP 页面。

---

### M2 闸门与最小只读连接

**目标**：八类目标各有"最小只读"实现（网页测试连接所需），白名单与危险清单双闸门生效，拒绝路径确认无外呼；连接池、超时、包络、审计骨架就位。

**前置**：M1。

**任务**

- [x] M2.1 `guards/protocol.py`（`Decision` 与 `check_*` 签名）+ `guards/forbidden.py`（跨组件危险常量）（6.2/6.6）。
- [x] M2.2 `guards/mysql.py`：sqlglot（`dialect="mysql"`）AST 白名单；危险清单含 `EXPLAIN ANALYZE`、系统库、无 WHERE 的排序/聚合、`SLEEP`/`BENCHMARK`/`GET_LOCK` 等（6.3/6.6）。
- [x] M2.3 其余七个 guard：Mongo、ES、Redis、GitLab、RabbitMQ、Kafka、CLS 的白名单与危险清单（6.3/6.6）。
- [x] M2.4 `connectors/base.py`：超时、行/字节截断、统一包络、审计快照、每 target 连接池与并发（读 `target_max_concurrency`）/9.3）。
- [x] M2.5 八类最小只读连接器：MySQL `SELECT 1`（连接后设事务只读、`max_execution_time`、`sql_select_limit`）、Mongo `ping`、ES 集群健康、Redis `PING`、GitLab 当前用户、RabbitMQ overview、Kafka 元数据、CLS 列主题（4.1 测试连接/6.6 兜底）。
- [x] M2.6 `catalog.py`：按 name 读配置、启用/类型/作用域校验、客户端池 key 为 `(target_id, updated_at)`、配置保存后失效（5.2/9.3）。
- [x] M2.7 无外呼测试框架：连接工厂桩、socket 桩、计数假服务（6.5）。
- [x] M2.8 危险清单拒绝用例：每组件至少一条管理类、一条高开销类（6.6/12.1）。

**交付物**：`guards/` 八组、`connectors/` 八组骨架、`catalog.py`、无外呼测试框架。

**验证目标**

| 编号 | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| V2.1 | 白名单正例 | 直接调用 guard 函数（不联网） | 允许并返回规范化结果 |
| V2.2 | 白名单反例 | planning 6.4 矩阵逐条 | `GUARD_REJECTED`，连接次数 0 |
| V2.3 | 危险清单反例 | planning 6.6 清单逐条 | `DANGEROUS_OPERATION`，连接次数 0 |
| V2.4 | 八类测试连接 | 夹具目标 + 连接器桩（八类）；真实连通性留到 M4/M5 手测 | 成功写回 `last_test_*`；失败摘要不含密钥 |
| V2.5 | 并发上限 | 同一 target 并发 11 次调用（配置 10） | 上游并发 ≤ 10，其余排队；超时返回 `UPSTREAM_TIMEOUT` |
| V2.6 | 配置变更失效 | 修改目标后调用 | 使用新客户端（桩计数可证） |
| V2.7 | 包络完整 | 任一连接器返回 | planning 8.1 的 11 个顶层键齐全 |
| V2.8 | MySQL 会话兜底 | 用桩记录连接初始化语句 | 执行 `transaction_read_only`、`max_execution_time`、`sql_select_limit` |

**退出条件**：V2.1–V2.8 全过；八类拒绝用例都能证明"没有发出网络请求"。

**注意**：M2 的"测试连接"是网页 M3 的前置能力；M2 结束时通过测试代码调用连接器，不依赖网页。

---

### M3 配置台网页与 MCP 接入（第一期收口）

**目标**：人能在网页里管八类目标与系统配置，三个客户端能连上 `/mcp` 看到 `systems_status`；第一期验收清单全部满足。

**前置**：M2。

**任务**

- [x] M3.1 `web/routes.py`：planning 4.1 全部路由（含 `/settings`、删除确认页、`/healthz` 已在 M0）。
- [x] M3.2 `web/forms.py`：表单解析与校验（名称规则、多行列表、公共字段、`type` 不可变）（4.2）。
- [x] M3.3 `web/views.py` + `web/templates/`：`TargetView`（密钥只暴露字段名）、列表/新建/编辑/删除确认/系统配置页，Jinja2 自动转义（4.3/4.4/4.5）。
- [x] M3.4 测试连接按钮接 M2 能力，结果落库并在列表展示（4.1）。
- [x] M3.6 MCP：注册 `systems_status`，写服务器说明，声明 `readOnlyHint`（8.4/8.8/8.9）。
- [x] M3.7 三客户端接入说明：Cursor / Codex / DeepSeek Harness 配置示例（3.4）。
- [x] M3.8 冒烟脚本扩展：起服务 → 客户端连 `/mcp` → 列工具 → 调 `systems_status`（12.1）。
- [x] M3.9 审计清理任务：启动 60 秒首跑、每小时一轮，按保留期分批删除且不写审计（9.6/12.2）。
- [x] M3.10 跑完第一期验收清单（12.2）。

**交付物**：`web/` 全套、`systems_status`、客户端接入文档、第一期验收记录。

**验证目标**

| 编号 | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| V3.1 | 网页 CRUD | 八类目标各建一个，再做编辑/停用/启用/删除 | 重定向与列表状态正确；停用目标在 `systems_status` 中标为停用 |
| V3.2 | 密钥不回显 | 查看列表页、编辑页、HTML 源码 | 无明文、无掩码串，只有"已设置/未设置" |
| V3.3 | 密钥三态 | 留空、勾选清除、填新值 | 行为符合 4.3；库里密文相应变化 |
| V3.4 | 表单校验 | 非法名称、越界上限、未知 `type` | 400 + 字段错误；库中不新增 |
| V3.5 | 系统配置页 | 改 90→30、10→5 保存；再提交非法值 | 保存成功并有 `settings.update` 审计；非法值 400 |
| V3.6 | 跨站防护 | 伪造 `Origin` 提交表单 | 403，数据不变 |
| V3.7 | MCP 内存测试 | `fastmcp.Client` 列工具并调 `systems_status` | 工具名稳定、返回包络正确、`readOnlyHint=true` |
| V3.8 | 三客户端手测 | Cursor / Codex / DeepSeek Harness 各连一次 | 都能列出工具并调通 `systems_status` |
| V3.9 | 第一期验收 | planning 12.2 全部勾选 | 全部通过，未验证项写明原因 |
| V3.10 | 文档同步 | 人工核对 | README 用过即更新；本文件状态更新 |

**退出条件**：V3.1–V3.7、V3.9、V3.10 全过；V3.8 有客户端环境则过，没有则在收口记录里登记"未验证（缺客户端）"；planning 12.2 无未解释的未勾选项。

**注意**：此时只有 `systems_status` 一个工具，客户端清单里出现别的工具说明注册顺序有问题。

---

### M3.5 配置台视觉与主题重构

**目标**：把配置台从"可用"提升到"像一个成熟内部产品"——统一设计系统、明暗两套主题（默认跟随系统）、更好的信息层级与操作反馈，同时保持零 JS 与无构建链。

**前置**：M3。

**任务**

- [x] U1 设计 token 与组件样式：`web/static/app.css`（颜色/字体/间距/圆角/阴影、按钮/输入/表格/徽标/提示条/空状态/卡片），浅深两套。
- [x] U2 静态资源路由：`GET /static/app.css`，带 ETag 与短缓存；模板用 `?v=<hash>` 破缓存。
- [x] U3 三态主题：Cookie `drpanda_theme` + `POST /theme`（system/light/dark）+ `prefers-color-scheme`，服务端渲染 `data-theme`，无闪烁、零 JS。
- [x] U4 页面骨架：顶栏（品牌/导航/版本/主题切换）、页面头、跳过链接、语义 landmark、焦点样式。
- [x] U5 列表页重构：统计条、搜索、类型筛选、单表、状态徽标、密钥异常提示、空状态与无结果态。
- [x] U6 类型选择页（`/targets/new` 无 type）。
- [x] U7 表单重构：两栏 + 分区卡片 + 顶部错误摘要 + 锚点 + 密钥三态 + 底部操作条。
- [x] U8 设置页/删除确认/统一 400/404 错误页。
- [x] U9 反馈与响应式：`?flash=...` 成功/失败提示；≤900px 表格转卡片、≤640px 单列。
- [x] U10 可访问性与验收：`aria-current`/`aria-pressed`/`aria-invalid`/`aria-live`、`scope`、对比度自动测试、键盘走查、截图基线。

**交付物**：设计系统与页面重构、`docs/ui-design.md`、主题与静态资源路由、视觉基线截图、验证记录。

**验证目标**

| 编号 | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| VU1 | 主题跟随与切换 | 无 Cookie 打开页面；`POST /theme` 切浅/深/系统 | 无 Cookie 无 `data-theme` 且跟随系统；手选后刷新保持；清除后回到系统；无闪烁 |
| VU2 | 两套主题对比度 | `pytest tests/test_ui_contrast.py` | 正文/次级/语义色 ≥4.5:1，两套 token 全过 |
| VU3 | 三宽度无溢出 | 无头浏览器检查 `scrollWidth == innerWidth`；1440/1024/390 | 无横向滚动；表格在窄屏转卡片 |
| VU4 | 键盘与读屏语义 | Tab 走查 + 检查 skip link、焦点环、`aria-*`、`scope` | 焦点顺序合理、焦点可见、关键语义齐全 |
| VU5 | 零 JS 与无外部资源 | 页面不含 `<script>`；CSS 无 `@import`/外部 URL；断网可用 | 全部页面与操作不依赖 JS；零外部请求 |
| VU6 | 视觉基线 | 浅/深 × 桌面/移动截图 | 无重叠、无截断、状态可辨 |
| VU7 | 回归 | `pytest -q` + 冒烟脚本 | 既有 294+ 测试全绿、冒烟通过 |
| VU8 | 文档同步 | 人工核对 | planning 4.1/4.4、`docs/ui-design.md`、README、本文件与验证记录同步 |

**退出条件**：VU1–VU8 全过；`docs/verify/M3.5.md` 记录证据；截图基线入库。

**注意**：主题用 Cookie 而非 JS，代价是切换会整页刷新；这是为了守住"零 JS"契约与无闪烁。后续若引入渐进增强 JS，需先改 planning 4.4。

---

### M4 日志到代码

**目标**：CLS 与 GitLab 五个工具可用，`investigate_error` 上线；这两类组件的白名单与危险规则有拒绝用例；多数报错可在此阶段完成排查。

**前置**：M3.5。

**任务**

- [x] M4.1 CLS guard：检索与只读描述白名单、时间窗规则、主题作用域、危险清单（6.3/6.6）。
- [x] M4.2 CLS 连接器与两个工具：`cls_search`、`cls_context`（8.4）。
- [x] M4.3 GitLab guard：只 GET、项目作用域、搜索必须带 term（6.3/6.6）。
- [x] M4.4 GitLab 连接器与三个工具：`gitlab_search_code`、`gitlab_get_file`、`gitlab_blame`（8.4）。
- [x] M4.5 `tool.call` 审计：工具名、target、参数摘要（截断 200 字符）、返回条数、耗时、错误码，不含密钥（5.4/9.1）。
- [x] M4.6 `prompts.py` 的 `investigate_error` 完整版；schema 步骤标注"第三期上线前跳过"（8.7）。
- [x] M4.7 CLS/GitLab 拒绝用例：管理类与高开销类各至少一条，断言无外呼（6.5/6.6）。
- [x] M4.8 真实只读凭证手测（用户提供时执行）：一次从日志到代码的完整链路（13.1 第二期验收）。

**交付物**：CLS 与 GitLab 连接器、五个工具、prompt、拒绝用例、手测记录。

**验证目标**

| 编号 | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| V4.1 | 工具清单 | `fastmcp.Client` 列工具 | 6 个，名称与 planning 8.4 一致 |
| V4.2 | 时间窗规则 | 缺时间窗、窗口 25h | `INVALID_ARGUMENT` |
| V4.3 | 主题作用域 | 未授权主题 | `SCOPE_DENIED` |
| V4.4 | 只读闸门 | 构造写类 CAT 接口调用 | `GUARD_REJECTED`，无外呼 |
| V4.5 | 截断与包络 | 大结果、小上限 | `truncated=true`，`notes` 说明，顶层键齐全 |
| V4.6 | prompt 内容 | 调用 `investigate_error` | 返回排查顺序，含"先看结构"与"不猜"要求 |
| V4.7 | 工具审计 | 调用后查 `audit` | 有 `tool.call`，无密钥，含条数与耗时 |
| V4.8 | 真实链路 | 用户只读凭证 | 能搜到日志并定位到文件；失败时登记未验证原因 |

**退出条件**：V4.1–V4.7 必须过；V4.8 有凭证则过，无凭证则在收口记录里登记为"未验证（缺凭据）"，不得标记通过。

**注意**：手测只连用户明确提供只读凭证的环境；不在仓库或日志里留真实凭据。

---

### M5 数据面

**目标**：MySQL、Mongo、Elasticsearch、Redis 十七个工具可用（含四个 schema 发现工具），四类组件的白名单与危险清单齐全。

**前置**：M4。

**任务**

- [x] M5.1 MySQL：guard 完整版（sqlglot AST + 危险清单 + 系统库 + 无 WHERE 排序/聚合）、连接器 `query/explain/processlist/tables/describe`（6.3/6.6/8.5）。
- [x] M5.2 Mongo：命令与阶段白名单、`$match` 前置规则、JS 执行与 `allowDiskUse`/`hint` 拒绝、连接器 `collections/find/aggregate/stats`（6.3/6.6/8.5）。
- [x] M5.3 Elasticsearch：方法+路径白名单、脚本/深分页/大小/高基数聚合拒绝、连接器 `mapping/search/health/index_stats`（6.3/6.6/8.5）。
- [x] M5.4 Redis：命令白名单、无界范围拒绝、长度探测、连接器 `get/scan/info/slowlog`（6.3/6.6/8.5）。
- [x] M5.5 十七个工具的参数、包络、截断与错误码（8.1–8.5）。
- [x] M5.6 四类组件危险清单拒绝用例（管理类 + 高开销类各一条以上）（6.6/12.1）。
- [x] M5.7 上限与并发验证：行、字节、超时、`target_max_concurrency`（8.3/9.3）。

**交付物**：四类连接器与 guard、十七个工具、拒绝用例、上限用例。

**验证目标**

| 编号 | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| V5.1 | 工具清单 | 内存客户端 | 23 个，名称稳定 |
| V5.2 | MySQL 白名单 | planning 6.4 MySQL 行 | 正例放行、反例 `GUARD_REJECTED` |
| V5.3 | MySQL 危险清单 | `EXPLAIN ANALYZE`、`SELECT SLEEP(10)`、无 WHERE 排序/聚合、系统库 | 全部 `DANGEROUS_OPERATION`，无外呼 |
| V5.4 | 强制 LIMIT | 不带 LIMIT 的 SELECT | 实际执行语句含 LIMIT，返回 ≤ `max_rows` |
| V5.5 | Mongo 阶段规则 | `$group` 前无 `$match`、`$where`、`allowDiskUse` | 全部拒绝 |
| V5.6 | ES 放大规则 | 带 `script` 的查询、`from+size>10000`、`size>max_rows` | 全部拒绝 |
| V5.7 | Redis 放大规则 | `LRANGE 0 -1`、`SCAN COUNT 1000`、`MONITOR` | 全部拒绝 |
| V5.8 | schema 工具范围 | 允许库/索引外的请求 | `SCOPE_DENIED`；返回只含允许范围 |
| V5.9 | 截断 | 构造超过行/字节上限的结果 | `truncated` 正确，`notes` 有说明 |
| V5.10 | 并发与超时 | 11 并发（配置 10）、慢上游 | 排队后 `UPSTREAM_TIMEOUT`，无超发 |
| V5.11 | 会话兜底 | 桩记录连接初始化 | 事务只读、`max_execution_time`、`sql_select_limit` 已设置 |

**退出条件**：V5.1–V5.11 全过；四类组件均至少有管理类与高开销类拒绝用例各一条。

**注意**：schema 工具只用 `SHOW` 类、`listCollections`/`collStats`、`GET mapping/settings` 实现，不查 `information_schema`。

---

### M6 消息面

**目标**：RabbitMQ 与 Kafka 五个工具可用，消息类危险清单与拉取上限生效，工具清单补齐到 28 个。

**前置**：M5。

**任务**

- [x] M6.1 RabbitMQ guard（只 GET、拒绝 purge/publish/ack/策略）与连接器（`rabbit_queues`、`rabbit_queue`）（6.3/6.6/8.6）。
- [x] M6.2 Kafka guard（描述类、拉取上限、单分区、offset 不早于 low watermark）与连接器（`kafka_lag`、`kafka_offsets`、`kafka_peek`）（6.3/6.6/8.6）。
- [x] M6.3 两类组件的危险清单拒绝用例（6.6/12.1）。
- [x] M6.4 工具参数、包络、截断、错误码收口（8.1–8.6）。

**交付物**：RabbitMQ 与 Kafka 连接器、五个工具、拒绝用例。

**验证目标**

| 编号 | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| V6.1 | 工具清单 | 内存客户端 | 28 个，名称稳定 |
| V6.2 | RabbitMQ 只读 | purge、publish、改策略请求 | `GUARD_REJECTED`，无外呼 |
| V6.3 | Kafka 消费组隔离 | 桩记录客户端行为 | 不加入消费组、不提交 offset、不创建生产者 |
| V6.4 | offset 边界 | `kafka_peek` 请求早于 low watermark | 拒绝（`DANGEROUS_OPERATION` 或 `INVALID_ARGUMENT`） |
| V6.5 | 拉取上限 | 构造超上限条数/字节 | `truncated` + `notes`，条数受控 |
| V6.6 | 队列/位点结果 | 假服务返回 | 字段与 planning 8.6 一致 |

**退出条件**：V6.1–V6.6 全过；消息类工具不产生任何写入或消费组副作用。

**注意**：Kafka 的 `kafka_peek` 只在保留范围内的位点拉取；实现时把 low watermark 作为硬校验，不依赖调用方传参。

---

### M7 登录

**目标**：网页与 `/mcp` 使用同一套身份验证，审计记录到人；工具实现、表结构、只读与危险规则不变。

**前置**：M6。

**任务**

- [x] M7.1 users 表、安装状态、首次安装向导（admin 密码 + 配置库选择/测试）。
- [x] M7.2 网页登录、签名 Session、CSRF、审计 actor=admin。
- [x] M7.3 `/mcp` Bearer Token 与独立 401。
- [x] M7.4 Session 有效期进入系统配置，默认 720 分钟。
- [x] M7.5 远程访问显式开关 + HTTPS public URL；非 loopback 未安装仍拒绝。
- [x] M7.6 真实 MySQL/PostgreSQL 安装联调通过；远程 TLS 反向代理实机验收待做。
- [x] M7.7 `/me` 账号页、修改密码、多 MCP Token 创建/物理删除/分页。
- [x] M7.8 前端约束调整为服务端优先 + 局部渐进增强；原生 dialog 与复制脚本落地。
- [ ] M7.7 文档最终收口与三客户端带 Authorization header 手测。

**交付物**：认证中间件、审计 actor 改造、回归记录、文档更新。

**验证目标**

| 编号 | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| V7.1 | 未认证拦截 | 无凭证访问 `/` 与 `/mcp` | 均 401 |
| V7.2 | 认证后可用 | 带凭证访问网页与调用工具 | 正常；工具清单不变 |
| V7.3 | 审计到人 | 调用工具后查 `audit` | `actor` 为真实身份 |
| V7.4 | 契约未变 | 对比 M6 末与 M7 末的工具名/包络/表结构 | 无差异 |
| V7.5 | 全量回归 | `uv run pytest -q` | 全绿 |

**退出条件**：V7.1–V7.5 全过；只读与危险规则回归用例仍通过。

**注意**：不在第一版引入半套 Token；认证失败与配置库故障要能区分。

## 6. 需求追溯矩阵

用来确认"规划里的每一条都有人做、有人验"。

| planning 章节 | 内容 | 里程碑 |
|---|---|---|
| 3.1–3.3、3.5 | 形态、启动、环境变量、安全基线 | M0（骨架）、M1（密钥/迁移）、M3（收口） |
| 3.4 | 三客户端接入 | M3 |
| 3.6 | 无登录边界 | 全局约束 G1/G9 |
| 4.1–4.5 | 网页路由、校验、密钥、风格、系统配置 | M3 |
| 5.1–5.8 | 配置库、接口、表、事务、迁移、方言、契约、加密 | M1 |
| 6.1–6.6 | 只读检查顺序、闸门、白名单、拒绝矩阵、无外呼、危险清单 | M2（框架）+ M4/M5/M6（各组件） |
| 7 | 八类目标字段与范围 | M1（存储）、M3（表单）、M5（连接器） |
| 8.1–8.3、8.9 | 包络、错误码、上限、工具元信息 | M2 |
| 8.4 | 第一批工具 | M3（`systems_status`）、M4（其余五个） |
| 8.5 | 第二批工具 | M5 |
| 8.6 | 第三批工具 | M6 |
| 8.7 | `investigate_error` | M4 |
| 8.8 | 服务器说明 | M3 |
| 9.1–9.2 | 日志、健康检查 | M0（骨架）、M1（db 字段）、M3（收口） |
| 9.3 | 连接池与并发 | M2 |
| 9.4 | 关闭 | M2 |
| 9.5 | 故障行为 | 各里程碑对应项 |
| 9.6 | 审计清理 | M1（实现）、M3（页面验证） |
| 10 | 代码结构 | 各里程碑按模块 |
| 11 | 依赖与工程准备 | M0 |
| 12.2 | 第一期验收清单 | M3 |
| 14 | 未决事项 | 不阻塞；确认后先改 planning 再改本文 |

## 7. 验证方法速查

| 类型 | 怎么验 | 用在哪 |
|---|---|---|
| 单元 | `uv run pytest -q` | 闸门、危险清单、校验、打码、加密 |
| 契约 | `uv run pytest -q tests/test_store_contract.py` | M1 起 |
| 拒绝无外呼 | `uv run pytest -q tests/test_guards_no_network.py` | M2 起每个组件 |
| 网页 | `uv run pytest -q tests/test_web.py` + 浏览器手测 | M3 |
| MCP | 内存客户端测试 + 三客户端手测 | M3 起 |
| 落盘检查 | `sqlite3 data/dr-panda.sqlite "select ..."` + `grep` | M1 |
| 冒烟 | `uv run python scripts/smoke.py` | M0 起 |
| 手工链路 | 浏览器 / curl / 真实只读凭证 | M3、M4 |

## 8. 状态跟踪

| 编号 | 里程碑 | 状态 | 备注 |
|---|---|---|---|
| M0 | 工程地基 | 已完成 | 验证记录见 [docs/verify/M0.md](verify/M0.md) |
| M1 | 配置库与系统配置 | 已完成 | 验证记录见 [docs/verify/M1.md](verify/M1.md) |
| M2 | 闸门与最小只读连接 | 已完成 | 验证记录见 [docs/verify/M2.md](verify/M2.md) |
| M3 | 配置台网页与 MCP 接入 | 已完成 | 验证记录见 [docs/verify/M3.md](verify/M3.md) |
| M3.5 | 配置台视觉与主题重构 | 已完成 | 验证记录见 [docs/verify/M3.5.md](verify/M3.5.md) |
| M4 | 日志到代码 | 已完成 | 验证记录见 [docs/verify/M4.md](verify/M4.md) |
| M5 | 数据面 | 已完成 | 验证记录见 [docs/verify/M5.md](verify/M5.md) |
| M6 | 消息面 | 已完成 | 验证记录见 [docs/verify/M6.md](verify/M6.md) |
| M7 | 登录 | 未开始 | |

状态取值：未开始 / 进行中 / 已完成 / 阻塞（阻塞时备注写具体原因与待决事项）。

## 9. 每个里程碑的收口要求

- 代码：任务清单全部勾选，仓库可正常启动与测试。
- 测试：本里程碑的自动化验证全绿；手工验证有记录。
- 文档：契约有变先改 `planning.md`；使用方式有变改 README；本文件状态与备注更新。
- 证据：每个验证项留一条可复现记录（命令与输出摘要，或页面截图）。
- 未验证项：依赖真实凭据或外部环境的项，在备注里登记"未验证 + 原因"，不得当作通过。
- 回归：M3 之后每个里程碑收口都要跑全量 `pytest`，确认旧工具、只读与危险规则没被破坏。

## 10. 与规划文档的关系

- 本文只是 planning.md 的任务拆解，不新增或修改契约；冲突以 planning.md 为准。
- 规划变更时：先改 planning.md 对应章节，再同步本文的任务、验证目标与追溯矩阵。
- 本文故意不含排期与时间，任务顺序只表示依赖关系，不表示工期。
