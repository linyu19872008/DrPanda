# Mongo 高级认证联调（X.509 / replica set）

本记录覆盖 Docker 社区镜像能真实跑通的部分；LDAP / AWS IAM / OIDC / `mongodb+srv` 依赖企业版、云服务或真实 DNS，未伪造。

## 实现方式

- 不新增 Mongo 专用认证字段，继续用 `auth_mode=uri` + URI 参数透传：
  - X.509：`authMechanism=MONGODB-X509&authSource=$external`
  - replica set：`replicaSet=drpanda-rs`
- target 级 TLS/CA/客户端证书字段继续生效；X.509 使用这些字段提供客户端证书。

## Docker 环境

- `drpanda-mongo-x509`（17021）：`--auth --tlsMode requireTLS`，`$external` 用户 `CN=drpanda-client`。
- `drpanda-mongo-rs`（27017）：单节点 replica set `drpanda-rs`。
- 证书由测试 CA 签发；应用不设置 `SSL_CERT_FILE`。

## 结果

| 场景 | 结果 |
|---|---|
| X.509 target（URI + 客户端证书） | `mongo_find` 返回 1 条 |
| X.509 无客户端证书 | `UPSTREAM_UNAVAILABLE` |
| replica set target（`replicaSet=drpanda-rs`） | `mongo_find` 返回 1 条 |
| `check_mongo_advanced.py` | **3/3 通过** |

## 明确阻塞

| 方式 | 为什么不能本地 Docker 验证 |
|---|---|
| LDAP | MongoDB Enterprise 功能；社区镜像不提供 LDAP 认证 |
| AWS IAM | 需要 MongoDB Atlas/AWS 凭证，不是本地服务 |
| OIDC | 需要 MongoDB Enterprise/Atlas 与 IdP |
| `mongodb+srv` | 需要真实 DNS SRV 记录；本地 Docker 无法提供 |

这些方式在 URI 模式下可以透传参数，但没有真实服务验证，**不能宣称可用**。要验证需要相应企业版/Atlas 沙箱和凭证。

## 复现

```bash
bash scripts/integration/mysql-tls/gen-certs.sh
docker compose -f scripts/integration/compose.yaml up -d
uv run dr-panda-mcp   # 不设置 SSL_CERT_FILE
# 另开终端
bash scripts/integration/register_targets.sh
bash scripts/integration/seed.sh
bash scripts/integration/prepare_mongo_auth.sh
bash scripts/integration/prepare_mongo_advanced.sh
uv run python scripts/integration/check_mongo_auth.py
uv run python scripts/integration/check_mongo_advanced.py
```

## 未覆盖

- LDAP / AWS IAM / OIDC / `mongodb+srv`（见上表）
- X.509 用户角色/证书轮换/CRL
- 多节点 replica set 故障切换与读偏好
