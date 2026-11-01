# Dr Panda MCP

线上排查用的只读 MCP 服务。人在网页里登记 MySQL、Mongo、Elasticsearch、Redis、GitLab、RabbitMQ、Kafka、CLS 的地址、凭证与允许访问的范围；Cursor、Codex、DeepSeek Harness 通过 Streamable HTTP 调用 `/mcp`，按 target 名使用只读排查工具。模型不能自己传入主机、账号或密码。

## 当前进度

已完成 **M0 工程地基**、**M1 配置库与系统配置**、**M2 闸门与最小只读连接**：

- 进程可启动，提供 `/healthz`（含配置库连通性）与 `/mcp` 端点，Host/Origin 校验与端口检查就位。
- 配置库三张表（`targets` / `audit` / `settings`）通过 Alembic 迁移创建；目标读写、密钥加密、系统配置校验、配置变更审计可用。
- 新密钥首次启动自动生成；库中有密文但密钥缺失或不匹配时拒绝启动。
- 八类组件都有只读闸门与最小只读探测（测试连接）；管理/变更命令由白名单拦截，高开销操作由危险清单拦截，二者都在建立连接之前判定。

网页、MCP 工具与真实上游连通性按 [docs/milestones.md](docs/milestones.md) 的 M3–M7 推进。

## 启动

```bash
uv sync                      # 安装依赖（默认 SQLite，开箱可用）
uv run dr-panda-mcp          # 默认监听 127.0.0.1:8111
curl -fsS http://127.0.0.1:8111/healthz
# {"ok": true, "version": "0.1.0", "db": "ok"}
```

首次启动会创建 `data/dr-panda.sqlite` 与 `data/secret.key`（权限 0600）。

MySQL / PostgreSQL 作为配置库时需要额外 extras：

```bash
uv sync --extra mysql        # asyncmy
uv sync --extra postgres     # asyncpg
# 排查组件按需安装：mongo / redis / kafka / cls
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DR_PANDA_HOST` | `127.0.0.1` | 监听网卡；只在本机或受控内网使用，不要暴露到公网 |
| `DR_PANDA_PORT` | `8111` | 网页与 `/mcp` 共用 |
| `DR_PANDA_DATABASE_URL` | `sqlite:///data/dr-panda.sqlite` | 配置库；支持 sqlite / mysql / postgresql，进程启动时自动补异步驱动 |
| `DR_PANDA_SECRET_KEY` | 未设置 | base64 编码的 32 字节密钥，用于加密目标密钥；未设置时使用 `data/secret.key` |
| `DR_PANDA_LOG_LEVEL` | `INFO` | 日志级别 |

**密钥备份**：`data/secret.key`（或 `DR_PANDA_SECRET_KEY`）与配置库同等重要，丢失后已登记的密钥不可恢复，只能重新录入。SQLite 迁移前会自动备份到 `data/backup/`（保留最近 5 份）。

## 客户端接入

三个客户端都只配置 URL，不配置命令（stdio 仅用于本机调试）：

```json
{
  "mcpServers": {
    "drpanda": {
      "url": "http://127.0.0.1:8111/mcp"
    }
  }
}
```

- Cursor：写入其 MCP 配置文件，字段名以客户端版本为准。
- Codex：`[mcp_servers.drpanda]` 下配置 `url`。
- DeepSeek Harness：`serverName` 用 `drpanda`，模型侧工具名形如 `mcp__drpanda__mysql_query`。

端口改过时，客户端 URL 使用同一个端口。

## 登记目标（网页在 M3 提供）

每类目标登记一次，工具调用时只传 `target` 名。八种类型：`mysql`、`mongo`、`elasticsearch`、`redis`、`gitlab`、`rabbitmq`、`kafka`、`cls`。每类都需要填主机或地址、凭证、允许访问的范围（库、索引、topic、项目、vhost），范围只缩小可读边界。名称只允许小写字母、数字与连字符，创建后不可改；密钥只存密文，不回显。

## 绝对只读与危险命令

- 八个排查组件的所有调用（含网页"测试连接"）都只读；账号即使有写权限也不会被使用。
- 只读白名单之外还有一条绝对规则：不执行管理/变更类命令，也不执行高开销操作（全表扫描、无界遍历、脚本执行、深度分页、大聚合等）。危险判定在建立连接之前完成，拒绝码 `DANGEROUS_OPERATION`。
- 每次调用受超时、行数、字节与每 target 并发上限约束；结果被截断会明确标记。

## 系统配置

两项运行策略存在配置库中，改动即审计；网页 `/settings` 在 M3 提供，后端校验与存储已就绪：

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
- [docs/verify/](docs/verify/)：各里程碑的验证记录
