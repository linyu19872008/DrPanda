# 真实上游 Docker 联调 03（P1：MySQL TLS / ES 多 host）

本记录只补 P1 的两项真实 Docker 验证；不改变既有里程碑状态。

## 环境

- 在 [integration-02](integration-02.md) 的 5 个容器基础上新增 `drpanda-elasticsearch-2`（host 19201），共 6 个 `drpanda-*` 容器。
- MySQL 使用 [scripts/integration/mysql-tls/gen-certs.sh](../../scripts/integration/mysql-tls/gen-certs.sh) 生成的测试 CA/服务端证书（SAN `DNS:localhost,IP:127.0.0.1`），挂载到 `/certs`，启动参数为 `--ssl-ca/--ssl-cert/--ssl-key`。
- 应用启动时设置 `SSL_CERT_FILE=/tmp/drpanda-mysql-certs/ca.pem`，让默认 `ssl.create_default_context()` 信任测试 CA。
- 目标：`drpanda-mysql-tls`（`ssl=on`）与 `drpanda-es-multi`（hosts 19200、19201）。

## 结果

| 项 | 验证 | 结果 |
|---|---|---|
| MySQL TLS | `mysql_query` 执行 `SHOW STATUS LIKE 'Ssl_cipher'` | TLS target 返回 `TLS_AES_256_GCM_SHA384`；非 TLS target 返回空 cipher |
| MySQL TLS 功能 | 测试连接 + `mysql_tables` | 测试连接 303、`last_test_ok=1`；`mysql_tables` 返回 2 张表 |
| ES 多 host 正常 | `es_search`（target 配 19200、19201） | 命中第一个节点的 5 条文档 |
| ES failover | 停 `drpanda-elasticsearch` 后调用 `es_search` / `es_health` | 自动切到 19201，返回第二节点文档；健康为 green |
| ES 全挂 | 再停 `drpanda-elasticsearch-2` 后调用 | `UPSTREAM_UNAVAILABLE: elasticsearch 所有 host 均不可用` |
| 恢复 | 启动两个 ES 容器 | 两个容器恢复 healthy，应用仍可调用 |

`scripts/integration/check_p1.py` 结果：**pass=4 / fail=0**。从空应用 `data/` 重新执行 `register_targets.sh`、`seed.sh`、`prepare_p1.sh` 后复跑仍为 4/4。

## 复现

```bash
bash scripts/integration/mysql-tls/gen-certs.sh
docker compose -f scripts/integration/compose.yaml up -d
SSL_CERT_FILE=/tmp/drpanda-mysql-certs/ca.pem uv run dr-panda-mcp
# 另开终端
bash scripts/integration/register_targets.sh
bash scripts/integration/seed.sh
bash scripts/integration/prepare_p1.sh
uv run python scripts/integration/check_p1.py
```

## 未覆盖

- MySQL 客户端证书/mTLS 已由 [integration-05.md](integration-05.md) 覆盖；`require_secure_transport=ON` 的强制 TLS 形态仍未覆盖
- target 级 CA 的客户端证书（当前只有服务端 CA 校验）
- ES HTTPS/TLS（本次多 host 仍是 HTTP + basic auth）
- ES failover 仅验证连接失败场景，未验证 5xx/超时的行为
- Kafka/CLS/GitLab 仍未验证
