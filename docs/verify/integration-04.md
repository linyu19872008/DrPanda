# target 级 CA 验证（MySQL / Elasticsearch）

本记录验证 [integration-03](integration-03.md) 中登记的缺口：私有 CA 不再依赖进程级 `SSL_CERT_FILE`。

## 实现

- MySQL / Elasticsearch 类型增加可选 `options.ca_pem`（PEM 文本，公开证书，不加密）。
- 表单：`ca_pem` 用 textarea 输入；PEM 解析失败、MySQL 配 CA 但未启用 SSL、ES 配 CA 但关闭 TLS 校验都会返回 400。
- 连接器：
  - MySQL：`ssl.create_default_context(cadata=target.options["ca_pem"])`
  - Elasticsearch：`httpx.AsyncClient(verify=SSLContext)`；CA 为空时仍按 `verify_tls` 布尔处理。
- 应用启动时**不设置** `SSL_CERT_FILE`，只靠 target 的 `ca_pem` 信任测试 CA。

## Docker 环境

- `drpanda-mysql`：13306，挂载测试 CA/服务端证书（SAN `DNS:localhost,IP:127.0.0.1`）。
- 新增 `drpanda-elasticsearch-tls`：19202，HTTPS + basic auth，证书由同一个测试 CA 签发；证书放到 ES 认可的 `config/certs` 目录。
- 应用与 target 由脚本创建，详见 [scripts/integration/README.md](../../scripts/integration/README.md)。

## 结果

| 项 | 结果 |
|---|---|
| MySQL target CA | `Ssl_cipher=TLS_AES_256_GCM_SHA384`，`mysql_tables` 正常 |
| MySQL 无 CA | `UPSTREAM_UNAVAILABLE: ... CERTIFICATE_VERIFY_FAILED ... self-signed certificate` |
| MySQL 测试连接（CA target） | 303，`last_test_ok=1` |
| ES target CA | `es_search` 返回 `drpanda tls target boom` |
| ES 无 CA | `UPSTREAM_UNAVAILABLE: ... unable to get local issuer certificate` |
| ES 测试连接（CA target） | 303，`last_test_ok=1` |
| 表单校验 | 非法 PEM → 400；CA 未启用 SSL → 400；合法 CA 落库并可编辑 |
| `check_target_ca.py` | **pass=4 / fail=0** |
| 从空 `data/` 重跑 | `register_targets.sh` → `seed.sh` → `prepare_p1.sh` → `prepare_target_ca.sh` → 两个检查均通过 |

## 复现

```bash
bash scripts/integration/mysql-tls/gen-certs.sh
docker compose -f scripts/integration/compose.yaml up -d
# 关键：不设置 SSL_CERT_FILE
uv run dr-panda-mcp
# 另开终端
bash scripts/integration/register_targets.sh
bash scripts/integration/seed.sh
bash scripts/integration/prepare_p1.sh
bash scripts/integration/prepare_target_ca.sh
uv run python scripts/integration/check_p1.py
uv run python scripts/integration/check_target_ca.py
```

## 未覆盖

- MySQL 客户端证书/mTLS、`require_secure_transport=ON`
- ES 客户端证书/mTLS
- target 级 CA 的证书链/过期/轮换与错误提示细节
- CA 文本大小上限 64KB 之外的大证书
