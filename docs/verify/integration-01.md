# 真实上游 Docker 联调 01

本记录只覆盖本机 Docker 起的真实上游基础冒烟；扩展参数/边界/失败矩阵见 [integration-02.md](integration-02.md)。不改变 M0–M6 的完成状态。

## 环境

- Docker Desktop Server 29.2.1（macOS）
- 服务版本 0.1.0，28 个工具
- 镜像：
  - `public.ecr.aws/docker/library/mysql:8.0.36` → `drpanda-mysql`，host `13306`
  - `public.ecr.aws/docker/library/mongo:7.0` → `drpanda-mongo`，host `17017`
  - `docker.elastic.co/elasticsearch/elasticsearch:8.13.4` → `drpanda-elasticsearch`，host `19200`
  - `public.ecr.aws/docker/library/redis:7.2-alpine` → `drpanda-redis`，host `16379`
  - `public.ecr.aws/docker/library/rabbitmq:3.13-management` → `drpanda-rabbitmq`，host `15673`
- 复现与清理见 [scripts/integration/README.md](../../scripts/integration/README.md)

所有容器、卷、数据库、集合、索引、key 前缀、queue 名称均以 `drpanda` 开头。密码为本地测试值。

从空 `data/` 重跑 `register_targets.sh` + `seed.sh` + 两个检查脚本，同样得到 19/19 工具通过、9/9 拒绝路径通过。

## 工具调用结果

5 个 target 登记成功（另建 `drpanda-mysql-small`，`max_rows=1` 用于截断验证），MCP 实际调用 **19 个工具全部通过**：

| 组件 | 工具 | 结果 |
|---|---|---|
| MySQL | `mysql_tables`、`mysql_describe`、`mysql_query`、`mysql_explain`、`mysql_processlist` | 5/5 通过；表 1 张、字段 5 个、`paid` 2 行、执行计划 1 行、会话列表可读 |
| MongoDB | `mongo_collections`、`mongo_find`、`mongo_aggregate`、`mongo_stats` | 4/4 通过；集合 1 个、`paid` 2 行、聚合计数 1 行、collStats 可读 |
| Elasticsearch | `es_mapping`、`es_search`、`es_health`、`es_index_stats` | 4/4 通过；4 个字段、命中 1 条、健康 green、索引统计 1 条 |
| Redis | `redis_get`、`redis_scan`、`redis_info`、`redis_slowlog` | 4/4 通过；string 值、2 个 key、INFO server、慢日志过滤后 1 条 |
| RabbitMQ | `rabbit_queues`、`rabbit_queue` | 2/2 通过；`drpanda-orders` 队列可读 |
| Kafka | `kafka_lag`、`kafka_offsets`、`kafka_peek` | **未执行**：镜像不可拉取，见"未验证" |

五个"测试连接"按钮全部成功（`target.test` 审计均为 `ok`）。

## 额外验证

| 项 | 结果 |
|---|---|
| 拒绝路径 | MySQL `SELECT SLEEP(10)` / 系统库、Mongo 无 `$match` 聚合、ES script、Redis 越前缀、Rabbit 越 vhost 等 9 条全部按预期拒绝，错误码 `DANGEROUS_OPERATION` / `SCOPE_DENIED` |
| ES 健康 | 单节点初始 yellow；将副本设为 0 后 green，`unassigned_shards=0` |
| Redis SLOWLOG 前缀 | 将阈值调 0 后触发 `GET drpanda:order:1` 与 `GET other:not-in-scope`，工具只返回前者，跨前缀条目被过滤 |
| MySQL 截断 | `drpanda-mysql-small`（`max_rows=1`）查询 `paid` 2 行，返回 `returned=1`、`truncated=true`、`reason=rows` |
| 审计 | `tool.call` 与 `target.test` 均落盘，含 target、工具名、返回条数、耗时、错误码 |
| 28 工具清单 | `systems_status` 统计 5 个 target、5 个启用 |
| 可重复性 | 清空应用 `data/` 后，按 `scripts/integration/README.md` 重新登记与检查，结果一致 |

## 未验证

- **Kafka**：`apache/kafka` 在 Docker Hub、ECR Public 与可用镜像站均不可拉取；按"拉不到就不做"的约定，不使用本地二进制替代，Kafka 三个工具的真实联调留待有可用镜像。
- **CLS / GitLab**：本轮只要求六个 Docker 组件；CLS 需要腾讯云凭证，GitLab 需要实例/token，均未验证。
- **MySQL TLS**：Docker MySQL 未开启 TLS，`ssl=true` 路径未在真实连接验证。
- **RabbitMQ 消息内容**：队列存在但消息数为 0；只验证了队列/详情元数据，未验证有消息时的计数/状态。
- **ES 安全形态**：本地为 HTTP 明文 + basic auth；未验证 HTTPS/TLS 与多 host 故障切换。
- 真实压测/并发未做；`target_max_concurrency` 仍由单测覆盖。

## 结论

MySQL / MongoDB / Elasticsearch / Redis / RabbitMQ 五类的真实连接、只读工具、范围拒绝、审计与截断行为均已跑通；未发现需要修改连接器的阻塞问题。Kafka 与 CLS/GitLab 仍是明确的功能空白；在补上这些之前，不能宣称"八类组件全部真实可用"。
