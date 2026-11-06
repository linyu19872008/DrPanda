# 上游 IO 上限、Redis ACL/TLS 与分页

本记录覆盖 2026-11-02 审计后的 P1：HTTP 响应流上限、Redis ACL/TLS/mTLS、Mongo/ES/CLS/GitLab 分页。GitLab / CLS / Kafka 真实上游仍阻塞，见末尾。

## 已完成

### HTTP 响应体上限

新增 `connectors/base.stream_http`：用 `httpx` 流式读取，超过 target `max_bytes` 默认报 `UPSTREAM_UNAVAILABLE`；只有 GitLab 文件读取允许截断到上限并标记 `truncated=true`。ES、GitLab JSON、Rabbit 队列列表都改走该函数。CLS 使用腾讯 SDK，未做 HTTP 层流式控制。

### Redis ACL / TLS / mTLS

- target 新增 `options.username`、`options.ca_pem`、`secret.client_cert`、`secret.client_key`。
- 连接器使用 `username`、`ssl=True`、`ssl_ca_data`；客户端证书写入临时文件，`close_client` 时删除。
- Docker：
  - `drpanda-redis-acl-tls`（16380）：ACL 用户 + TLS，`tls-auth-clients no`。
  - `drpanda-redis-acl-mtls`（16381）：ACL 用户 + TLS，客户端证书必填。
- 结果：ACL/TLS 与 ACL/mTLS 均能读取 `drpanda:order:1`；无客户端证书访问 mTLS 返回 `UPSTREAM_UNAVAILABLE`；`check_redis_tls.py` 3/3。

### 分页

| 工具 | 新增参数 | 说明 |
|---|---|---|
| `mongo_find` | `skip` | 0–10000，超过返回 `DANGEROUS_OPERATION` |
| `es_search` | `search_after` | JSON 数组，必须配合 `sort`，不能与 `from` 同用；行里返回 `_sort` |
| `cls_search` | `offset` | 0–10000，传给 SearchLog `Offset` |
| `gitlab_search_code` | `page` | 1–10000，传给 GitLab 分页 |

## 真实上游阻塞

| 组件 | 状态 |
|---|---|
| GitLab | 本机没有 GitLab 镜像，拉取体积/网络不可用；没有实例 URL 和 token，未伪装通过 |
| CLS | 没有腾讯云 SecretId/SecretKey 与日志主题，无法真实调用 |
| Kafka | 仍没有可用 Kafka 镜像；不使用本地二进制或 Redpanda 替代 |

因此这 8 个工具仍不能被标记为真实可用；代码单测和分页/认证字段校验只证明实现路径。

## 验证

- `check_redis_tls.py`：3/3
- 全量 `pytest`：通过
- `ruff`：通过
- 本轮 Redis 容器/app 已启动验证后停止清理
