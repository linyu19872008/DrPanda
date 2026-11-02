# 真实上游 Docker 联调

本目录只用于本机联调，所有容器、网络、卷、数据库、索引、topic/queue 都以 `drpanda` 开头。**密码是本地测试值，不要用于真实环境。**

## 启动

```bash
# 0. 生成 MySQL TLS 测试证书（/tmp/drpanda-mysql-certs）
bash scripts/integration/mysql-tls/gen-certs.sh

# 1. 起 11 个上游（MySQL TLS/mTLS + 4 个 ES + Mongo 无认证/TLS/mTLS；Kafka 暂不启动）
docker compose -f scripts/integration/compose.yaml up -d

# 2. 安装驱动
uv sync --extra mysql --extra mongo --extra redis --extra kafka

# 3. 起服务（默认 8111）
uv run dr-panda-mcp

# 4. 另开终端，登记 target + 补 ES/Redis/Rabbit 数据
bash scripts/integration/register_targets.sh
bash scripts/integration/seed.sh
bash scripts/integration/prepare_matrix.sh
bash scripts/integration/prepare_p1.sh
bash scripts/integration/prepare_target_ca.sh
bash scripts/integration/prepare_mtls.sh
bash scripts/integration/prepare_mongo_auth.sh

# 5. 跑基础检查、扩展矩阵、P1、target CA、mTLS、Mongo 认证
uv run python scripts/integration/check_tools.py
uv run python scripts/integration/check_refusals.py
uv run python scripts/integration/check_matrix.py
# MySQL TLS 与 ES 多 host（脚本会停/启 ES 容器）
uv run python scripts/integration/check_p1.py
uv run python scripts/integration/check_target_ca.py
uv run python scripts/integration/check_mtls.py
uv run python scripts/integration/check_mongo_auth.py
```

## 两套检查

- `check_tools.py`：5 类组件各工具的连通性冒烟（19 条）
- `check_refusals.py`：基础拒绝路径（9 条）
- `check_matrix.py`：integration-02 参数/边界/失败矩阵（69 条）
- `check_p1.py`：MySQL TLS 与 ES 多 host（4 条）
- `check_target_ca.py`：target 级 CA（MySQL/ES，4 条）
- `check_mtls.py`：MySQL REQUIRE X509 / ES 客户端证书（4 条）
- `check_mongo_auth.py`：Mongo none/password/uri/TLS（5 条）

## P1 与 target 级 CA

- MySQL 启用测试 CA/服务端证书（`mysql-tls/gen-certs.sh`）；`prepare_p1.sh` 给 `drpanda-mysql-tls` 直接写入 `ca_pem`，无需进程级 `SSL_CERT_FILE`。
- `prepare_target_ca.sh` 额外登记 MySQL/ES 的 CA 与无 CA 对照 target；`check_target_ca.py` 验证 target 级 CA 生效、无 CA 时证书校验失败。
- `prepare_mtls.sh` / `check_mtls.py` 验证 MySQL `REQUIRE X509` 用户和 ES `client_authentication=required`；无客户端证书必须失败。
- 两个 ES 容器 `drpanda-elasticsearch`（19200）与 `drpanda-elasticsearch-2`（19201），target `drpanda-es-multi` 配两个 host；停第一个验证 failover，停两个验证 `UPSTREAM_UNAVAILABLE`。

## 端口与凭证（仅本地）

| 组件 | 容器名 | 端口 | 账号 |
|---|---|---|---|
| MySQL | `drpanda-mysql` | 13306 | `drpanda_ro` / `drpanda_mysql_ro_pw`（SELECT/SHOW VIEW/PROCESS） |
| MongoDB | `drpanda-mongo` | 17017 | `drpanda_ro` / `drpanda_mongo_ro_pw`，authSource `drpanda`（password） |
| MongoDB 无认证 | `drpanda-mongo-noauth` | 17018 | 无认证，用于 auth_mode=none |
| MongoDB TLS | `drpanda-mongo-tls` | 17019 | TLS + 测试 CA，用于 auth_mode=none + tls |
| MongoDB mTLS | `drpanda-mongo-mtls` | 17020 | TLS + 客户端证书必填，用于 mTLS |
| Elasticsearch | `drpanda-elasticsearch` | 19200 | `elastic` / `drpanda_es_pw`，HTTP 明文、单节点 |
| Elasticsearch 2 | `drpanda-elasticsearch-2` | 19201 | 同上，用于多 host failover |
| Elasticsearch TLS | `drpanda-elasticsearch-tls` | 19202 | HTTPS + 测试 CA，用于 target 级 CA |
| Elasticsearch mTLS | `drpanda-elasticsearch-mtls` | 19203 | HTTPS + 客户端证书必填，用于 mTLS |
| Redis | `drpanda-redis` | 16379 | 密码 `drpanda_redis_pw`，key 前缀 `drpanda:` |
| RabbitMQ | `drpanda-rabbitmq` | 15673 | `drpanda` / `drpanda_rabbit_pw`，vhost `/` |

## Mongo 认证

- `prepare_mongo_auth.sh` 创建 noauth / URI / TLS / mTLS / 无证书对照 target；`check_mongo_auth.py` 验证 7 条。
- URI 模式只接受 `mongodb://` 或 `mongodb+srv://`，host/user/password 必须留空。
- `register_targets.sh` 的 `drpanda-mongo` 使用 `auth_mode=password`。

## Kafka 为什么没起

`apache/kafka`、Bitnami Kafka 在本机 Docker Hub/ECR Public/镜像站均不可用（拉取超时或不存在）。按"拉不到就先不做"的约定，本轮不启动 Kafka，也不使用本地二进制替代；`kafka_lag`/`kafka_offsets`/`kafka_peek` 的真实联调仍待有可用镜像时补。

## 清理

```bash
docker compose -f scripts/integration/compose.yaml stop
# 需要彻底删除容器与卷时：docker compose -f scripts/integration/compose.yaml down -v
```
