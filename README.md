# Dr Panda MCP

线上排查用的只读 MCP 服务。人在网页里登记 MySQL、Mongo、Elasticsearch、Redis、GitLab、RabbitMQ、Kafka、CLS 的地址、凭证与允许访问的范围；Cursor、Codex、DeepSeek Harness 通过 Streamable HTTP 调用 `/mcp`，按 target 名使用只读排查工具。模型不能自己传入主机、账号或密码。

## 当前进度

已完成 **M0–M7 基础**（工程地基、配置台、日志到代码、数据面、消息面、首次安装与登录认证）：

- 进程可启动，提供 `/healthz`（含配置库连通性）与 `/mcp` 端点，Host/Origin 校验与端口检查就位。
- 配置库包含 `users` / `targets` / `audit` / `settings` / `settings_history`，通过 Alembic 迁移创建；目标读写、密钥加密、系统配置校验、配置变更审计可用。
- 新密钥首次启动自动生成；库中有密文但密钥缺失或不匹配时拒绝启动。
- 八类组件都有只读闸门与最小只读探测（测试连接）；管理/变更命令由白名单拦截，高开销操作由危险清单拦截，二者都在建立连接之前判定。
- 浏览器打开 `http://127.0.0.1:8111/` 可登记/编辑/停用/删除目标、测试连接、修改系统配置。
- 配置台支持浅色/深色主题（默认跟随系统，Cookie 实现、零 JS），列表带统计/搜索/类型筛选，窄屏自动转卡片。
- 首次启动进入安装向导：设置 admin 密码、选择 SQLite/MySQL/PostgreSQL 配置库并测试连接；安装完成后网页登录，`/mcp` 使用安装完成页显示的 Bearer Token；Token 丢失可在“我的”页面输入当前密码重新生成。
- 默认只监听 `127.0.0.1` / `::1` / `localhost`；远程访问需 `DR_PANDA_ALLOW_REMOTE=1` + HTTPS `DR_PANDA_PUBLIC_URL`，且必须先在本机完成安装。
- 审计清理任务随进程启动（60 秒后首跑、每小时一轮）。
- 已用 Docker 真实联调 MySQL / MongoDB / Elasticsearch / Redis / RabbitMQ：19 个工具冒烟 + 69 条参数/边界/失败矩阵全部通过；MySQL TLS（含 target 级 CA 与 mTLS）、ES 多 host failover/TLS/mTLS、Mongo 无认证/密码/URI/TLS/mTLS、X.509、replica set 均已通过。Kafka 镜像不可用、CLS/GitLab 缺凭证，尚未真实联调。
- `/mcp` 已提供 28 个工具：`systems_status`；CLS 检索/上下文；GitLab 代码搜索/读文件/blame；MySQL 5 个；Mongo 4 个；Elasticsearch 4 个；Redis 4 个；RabbitMQ 2 个；Kafka 3 个。全部带 `tool.call` 审计，并提供 `investigate_error` prompt。

![配置台](docs/verify/assets/ui/light-index.png)

M7 首次安装、网页登录、`/me` 账号页和 `/mcp` Bearer 已实现；SQLite/MySQL/PostgreSQL 配置库安装均已真实联调，见 [m7-01.md](docs/verify/m7-01.md)；排查组件真实上游连通性需要对应 extras 与只读凭证。

## 启动

```bash
uv sync                      # 安装依赖（默认 SQLite，开箱可用）
uv run dr-panda-mcp          # 默认监听 127.0.0.1:8111
curl -fsS http://127.0.0.1:8111/healthz
# 浏览器打开 http://127.0.0.1:8111/：首次进入安装向导，完成后登录
# {"ok": true, "version": "0.1.0", "db": "ok"}
```

首次启动不会预置管理员：先进入安装向导，设置 admin 密码并选择配置库；完成后创建 `data/install.json`、`data/install.key`、`data/session.key` 与配置库加密密钥（权限 0600）。旧配置库可继续选择原 SQLite 路径以保留数据。

MySQL / PostgreSQL 作为配置库时需要额外 extras：

```bash
uv sync --extra mysql        # asyncmy
uv sync --extra postgres     # asyncpg
# 排查组件按需安装：mysql / mongo / redis / kafka / cls（GitLab 用 httpx）
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DR_PANDA_HOST` | `127.0.0.1` | 监听网卡；只在本机或受控内网使用，不要暴露到公网 |
| `DR_PANDA_PORT` | `8111` | 网页与 `/mcp` 共用 |
| `DR_PANDA_DATABASE_URL` | `sqlite:///data/dr-panda.sqlite` | 配置库 URL；首次安装后以 `data/install.json` 中选择的库为准 |
| `DR_PANDA_SECRET_KEY` | 未设置 | base64 编码的 32 字节密钥，用于加密目标密钥；未设置时使用 `data/secret.key` |
| `DR_PANDA_LOG_LEVEL` | `INFO` | 日志级别 |
| `DR_PANDA_ALLOW_REMOTE` | 未设置 | 显式允许非 loopback 监听；须先完成安装 |
| `DR_PANDA_PUBLIC_URL` | 未设置 | 远程访问的 HTTPS 公开地址 |

**备份**：`data/secret.key`（或 `DR_PANDA_SECRET_KEY`）、`data/install.json`、`data/install.key`、`data/session.key` 与配置库同等重要。丢失加密密钥后已登记的密钥不可恢复；丢失 install 状态需恢复备份。SQLite 仅在存在 pending migration 时备份到 `data/backup/`，保留数量由系统配置 `backup_keep_count` 控制（默认 20，范围 1–20）。

## 客户端接入

三个客户端都配置 URL + Authorization header（stdio 仅用于本机调试）：

```json
{
  "mcpServers": {
    "drpanda": {
      "url": "http://127.0.0.1:8111/mcp",
      "headers": {
        "Authorization": "Bearer <安装完成页显示的 MCP Token>"
      }
    }
  }
}
```

- Cursor：写入其 MCP 配置文件，字段名以客户端版本为准。
- Codex：`[mcp_servers.drpanda]` 下配置 `url` 与 header（字段名以客户端版本为准）。
- DeepSeek Harness：`serverName` 用 `drpanda`，模型侧工具名形如 `mcp__drpanda__mysql_query`。
- `/mcp` 未认证返回 401；网页登录 Session 不能代替 Bearer Token。

端口改过时，客户端 URL 使用同一个端口。

## 登记目标

每类目标登记一次，工具调用时只传 `target` 名。八种类型：`mysql`、`mongo`、`elasticsearch`、`redis`、`gitlab`、`rabbitmq`、`kafka`、`cls`。每类都需要填主机或地址、凭证、允许访问的范围（库、索引、topic、项目、vhost），范围只缩小可读边界。Mongo 需要显式选择认证方式：`none`（无认证）/ `password`（用户名密码）/ `uri`（完整连接串，适合 SRV、replica set、X.509 等高级选项）。

MySQL / Elasticsearch 可额外填 `CA 证书 PEM`（`ca_pem`）用于私有 CA，证书是公开材料，不加密、不回显在列表；配置 CA 时 MySQL 必须启用 SSL、ES 必须保持 TLS 校验。需要双向 TLS 时可再填客户端证书与私钥（加密保存，必须成对提供，当前不支持带口令私钥）。名称只允许小写字母、数字与连字符，创建后不可改；密钥只存密文，不回显。

## 绝对只读与危险命令

- 八个排查组件的所有调用（含网页"测试连接"）都只读；账号即使有写权限也不会被使用。
- 只读白名单之外还有一条绝对规则：不执行管理/变更类命令，也不执行高开销操作（全表扫描、无界遍历、脚本执行、深度分页、大聚合等）。危险判定在建立连接之前完成，拒绝码 `DANGEROUS_OPERATION`。
- 每次调用受超时、行数、字节与每 target 并发上限约束；结果被截断会明确标记。

## 系统配置

两项运行策略通过网页 `/settings` 修改，存在配置库中，改动即审计：

| 配置键 | 默认 | 范围 |
|---|---|---|
| `audit_retention_days` | 90 天 | 1–3650 |
| `target_max_concurrency` | 10 | 1–50 |

## 开发

```bash
uv run pytest -q                  # 单元/契约/网页/工具测试
uv run python scripts/smoke.py    # 冒烟：启动服务并探活
uv run ruff check .               # 静态检查
```

测试使用临时 SQLite 与临时密钥，不连接真实线上系统，不使用真实凭证。

## 文档

- [docs/planning.md](docs/planning.md)：方案与实现契约（接口、表结构、只读与危险规则、工具清单）
- [docs/milestones.md](docs/milestones.md)：里程碑拆分与每个检查点的验证目标
- [docs/ui-design.md](docs/ui-design.md)：配置台设计系统、主题机制与页面规格
- [docs/verify/](docs/verify/)：各里程碑的验证记录；[hardening-02.md](docs/verify/hardening-02.md) 记录 P0 安全收口；[settings-01.md](docs/verify/settings-01.md) 记录系统配置分组；[settings-02.md](docs/verify/settings-02.md) 记录真实 Chrome 截图/键盘走查；[sqlite-wal-01.md](docs/verify/sqlite-wal-01.md) 记录 SQLite WAL 可见性处理；[settings-03.md](docs/verify/settings-03.md) 记录 settings 表结构化改造；[i18n-01.md](docs/verify/i18n-01.md) 记录中英文 Web UI；[hardening-01.md](docs/verify/hardening-01.md) 记录 2026-11-02 复核硬化；[integration-01.md](docs/verify/integration-01.md) / [integration-02.md](docs/verify/integration-02.md) / [integration-03.md](docs/verify/integration-03.md) / [integration-04.md](docs/verify/integration-04.md) / [integration-05.md](docs/verify/integration-05.md) / [integration-06.md](docs/verify/integration-06.md) / [integration-07.md](docs/verify/integration-07.md) / [integration-08.md](docs/verify/integration-08.md) 记录真实 Docker 上游联调（基础冒烟 + 扩展矩阵 + TLS/多 host + target 级 CA + mTLS + Mongo 认证/高级认证 + Redis ACL/TLS/分页）
- [scripts/integration/](scripts/integration/)：本地 Docker 联调栈与检查脚本
