# Mongo 认证模式 / TLS 验证

本记录补齐 [integration-02](integration-02.md) 中 Mongo 只验证了用户名密码的缺口。

## 实现

- Mongo 新增 `options.auth_mode`：
  - `none`：无认证，只允许 host/port
  - `password`：host/port + user + password + auth_source
  - `uri`：完整 `mongodb://` / `mongodb+srv://` URI；host/user/password 必须留空
- 旧 target 没有 `auth_mode` 时按 `uri` → `password` → `none` 推断，连接器同样兼容。
- 新增 Mongo TLS 配置（与 MySQL/ES 对齐）：
  - `options.tls`、`options.ca_pem`
  - `secret.client_cert`、`secret.client_key`
  - 连接器生成临时 `tlsCAFile` / `tlsCertificateKeyFile`，用后删除。
- Driver `serverSelectionTimeoutMS` 取工具超时的 80%，让证书/认证错误先于工具级 deadline 返回，避免被误报成 `UPSTREAM_TIMEOUT`。

## Docker 环境

- `drpanda-mongo`（17017）：用户名密码认证，已有集成数据。
- 新增 `drpanda-mongo-noauth`（17018）：无认证，init 脚本写入 `drpanda_orders`。
- 新增 `drpanda-mongo-tls`（17019）：`--tlsMode requireTLS`，测试 CA 签发的服务端证书。
- 应用启动不设置 `SSL_CERT_FILE`，TLS target 使用自己的 `ca_pem`。

## 结果

| 场景 | 结果 |
|---|---|
| `auth_mode=none` 无认证 target | `mongo_collections` 返回 1 个集合 |
| `auth_mode=password` | `mongo_find` 返回 2 条 paid 文档 |
| `auth_mode=uri`（含 authSource 的完整 URI） | `mongo_find` 返回 2 条 |
| `auth_mode=none` + TLS + target CA | `mongo_find` 返回数据 |
| TLS target 无 CA | `UPSTREAM_UNAVAILABLE: CERTIFICATE_VERIFY_FAILED` |
| TLS + 客户端证书 target | `mongo_find` 返回数据 |
| mTLS target 无客户端证书 | `UPSTREAM_UNAVAILABLE` |
| 表单：URI 模式同时填 host | 400，提示必须留空 |
| 表单：password 模式缺密码 | 400 |
| 表单：none 模式填 user | 400 |
| `check_mongo_auth.py` | **7/7 通过** |

## 复现

```bash
bash scripts/integration/mysql-tls/gen-certs.sh
docker compose -f scripts/integration/compose.yaml up -d
uv run dr-panda-mcp   # 不设置 SSL_CERT_FILE
# 另开终端
bash scripts/integration/register_targets.sh
bash scripts/integration/seed.sh
bash scripts/integration/prepare_mongo_auth.sh
uv run python scripts/integration/check_mongo_auth.py
```

## 未覆盖

- X.509 与单节点 replica set 已由 [integration-07.md](integration-07.md) 覆盖
- LDAP / AWS IAM / OIDC / mongodb+srv 仍因企业版/云/DNS 依赖未验证
- 带口令的客户端私钥
