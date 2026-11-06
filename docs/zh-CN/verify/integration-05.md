# mTLS / 客户端证书验证（MySQL / Elasticsearch）

本记录在 [integration-04](integration-04.md) 的 target 级 CA 基础上，补客户端证书认证。

## 实现

- MySQL / Elasticsearch 新增可选加密密钥字段：
  - `secret.client_cert`（客户端证书 PEM）
  - `secret.client_key`（客户端私钥 PEM，不加密私钥）
- 两者必须同时提供或同时清空；MySQL 还要求 `ssl=true`，ES 要求 `verify_tls=true`。
- 表单用 textarea 录入 PEM，保存后不回显；私钥经 `secret_json` 加密落盘。
- 共用 `connectors/base.build_tls_context`：按 target CA 建 context，再把客户端证书/私钥写入临时文件调用 `load_cert_chain`，用完删除；不支持带口令私钥。
- Docker：
  - MySQL 用户 `drpanda_mtls` 使用 `REQUIRE X509`；
  - 新增 `drpanda-elasticsearch-mtls`（19203），`xpack.security.http.ssl.client_authentication=required`；
  - 客户端证书由同一个测试 CA 签发（`gen-certs.sh`）。

## 结果

应用启动**不设置** `SSL_CERT_FILE`，只依赖 target 的 `ca_pem` + 客户端证书。

| 项 | 结果 |
|---|---|
| MySQL mTLS target | `Ssl_cipher=TLS_AES_256_GCM_SHA384`，查询正常 |
| MySQL `REQUIRE X509` 用户但无客户端证书 | `UPSTREAM_UNAVAILABLE: Access denied ...` |
| ES mTLS target | `es_search` 返回 `drpanda mtls boom` |
| ES `client_authentication=required` 但无客户端证书 | `UPSTREAM_UNAVAILABLE: SSLV3_ALERT_BAD_CERTIFICATE` |
| 测试连接 | MySQL / ES mTLS 均 303、`last_test_ok=1` |
| 表单配对校验 | 只填证书或只填私钥 → 400；两者同时 → 303，密钥落库为加密字段 |
| `check_mtls.py` | **pass=4 / fail=0** |
| 从空 `data/` 重跑 | `prepare_mtls.sh` + `check_mtls.py` 通过 |

## 复现

```bash
bash scripts/integration/mysql-tls/gen-certs.sh
docker compose -f scripts/integration/compose.yaml up -d
uv run dr-panda-mcp   # 不要设置 SSL_CERT_FILE
# 另开终端
bash scripts/integration/prepare_mtls.sh
uv run python scripts/integration/check_mtls.py
```

## 未覆盖

- 带口令的客户端私钥
- 客户端证书链/过期/轮换
- MySQL `require_secure_transport=ON` 与客户端证书组合的强制形态
- ES 客户端证书与 API Key 组合（本次用 basic auth）
