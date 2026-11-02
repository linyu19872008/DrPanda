# 真实上游 Docker 联调 02（扩展矩阵）

在 [integration-01.md](integration-01.md) 的 19 条工具冒烟基础上，补充参数、边界、错误映射与截断矩阵。仍只覆盖本机 Docker 能起的五类组件。

## 环境

沿用 [scripts/integration/compose.yaml](../../scripts/integration/compose.yaml) 的 5 个 `drpanda-*` 容器；应用 `0.1.0`，登记 18 个 target：

- 6 个基础/小上限 target（`drpanda-mysql`、`-mysql-small`、`-mongo`、`-es`、`-redis`、`-rabbit`）
- 7 个扩展 target（`-mysql-wide`、`-es-wide`、`-es-small`、`-mongo-small`、`-redis-small`、`-rabbit-wide`、`-rabbit-small`）
- 5 个错误凭证 target（`-mysql-bad`、`-mongo-bad`、`-es-bad`、`-redis-bad`、`-rabbit-bad`）

Kafka/CLS/GitLab 未在本轮范围。所有数据与容器均以 `drpanda` 开头。

## 结果

`scripts/integration/check_matrix.py` 共 **69 条**，**69 条通过**（从空应用 `data/` 重新执行 `register_targets.sh`、`seed.sh`、`prepare_matrix.sh` 后复跑仍为 69/69）：

| 组件 | 通过/总数 | 覆盖 |
|---|---|---|
| MySQL | 17/17 | 默认/第二库、视图、混合类型、空结果、强制 LIMIT、截断；写/多语句/系统库/跨库/`SHOW DATABASES` 拒绝；未知表、错误凭证错误映射 |
| MongoDB | 14/14 | 集合、projection/sort、空结果、`$project`/`$sort`/`$lookup`、collStats/dbStats、截断；无 filter、`$group` 无 `$match`、`$out`、`$where`、库范围、错误凭证 |
| Elasticsearch | 15/15 | 嵌套 mapping、空索引、match/分页/sort、空结果、health、index stats、截断；size 上限、深分页、script、terms、非法 query body、索引范围、错误凭证 |
| Redis | 16/16 | string/list/set/zset/hash/TTL/缺失 key、SCAN、INFO 全量、slowlog 前缀、截断；超大 string/list、前缀、SCAN COUNT、错误凭证 |
| RabbitMQ | 7/7 | 有消息的队列、单队列详情、第二 vhost、截断；缺失队列 404、vhost 范围、错误凭证 |

补充确认：

- `rabbit_queues` 能读到 `drpanda-orders` 的 messages；`rabbit_queue` 详情一致
- Redis `SLOWLOG` 只返回含 `drpanda:` key 的条目
- 小上限 target 的 MySQL/ES/Mongo/Redis/Rabbit 截断均返回 `truncated=true` 且 `reason=rows`
- 错误凭证均为 `UPSTREAM_UNAVAILABLE`；Rabbit 缺失队列为 `UPSTREAM_NOT_FOUND`
- 错误信息中的密码被 `***` 打码（MySQL 错误示例可见）

## 复现

```bash
docker compose -f scripts/integration/compose.yaml start
uv run dr-panda-mcp
# 另开终端（首次需先清空应用 data/ 再启动服务）
bash scripts/integration/register_targets.sh
bash scripts/integration/seed.sh
bash scripts/integration/prepare_matrix.sh
uv run python scripts/integration/check_tools.py
uv run python scripts/integration/check_refusals.py
uv run python scripts/integration/check_matrix.py
```

## 仍未覆盖

- MySQL TLS 与 ES 多 host failover 已由 [integration-03.md](integration-03.md) 覆盖；ES HTTPS/TLS 仍未覆盖
- 真实并发排队与超时（目前只由单测覆盖；短 timeout 的错误凭证 target 会先触发 `UPSTREAM_TIMEOUT`，属整调用优先级的预期现象，故错误凭证 target 用 10s 超时验证认证映射）
- `es_search` 未暴露顶层 `track_total_hits` 参数，该危险规则只能由 guard 单测覆盖
- `rabbit_queue` 的 summary 里 vhost `/` 未编码，显示为 `///`，不影响结果但可读性一般
- Kafka、CLS、GitLab
