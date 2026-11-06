# 上游错误分类 01 · 验证记录

背景：审计里 `mysql 查询失败：(1054, "Unknown column 'roomnumber' in 'field list'")` 被标成
`UPSTREAM_UNAVAILABLE`（上游不可用），语义错位——这是上游拒绝了查询，不是服务故障。按确认的方案
新增两个错误码并细化四个连接器的分类；`UPSTREAM_UNAVAILABLE` 中文标签改为「上游不可达」；不新增
`UPSTREAM_BUSY`；历史审计不回填。

## 变更

| 层 | 改动 |
|---|---|
| 错误码 | `errors.py`：新增 `UPSTREAM_QUERY_ERROR`、`UPSTREAM_AUTH` 常量与 `UpstreamQueryError` / `UpstreamAuthError` 异常类，加入 `ALL_CODES`；`tools/base.py` 的 `_ERROR_CODES` 注册两码 |
| 分类器 | 新增 `connectors/classify.py`：按 MySQL errno/SQLSTATE、Mongo error code/异常类名、ES HTTP 状态、Redis 异常类名/错误前缀，映射到 连接/超时/查询/认证 四类；只做鸭子类型判断，不 import 驱动 |
| MySQL | 探测与查询的 catch-all 改为 `classify.mysql_error`：1054/1064/1146 等 → `UPSTREAM_QUERY_ERROR`，1044/1045/1698 → `UPSTREAM_AUTH`，1205/1213 → `UPSTREAM_TIMEOUT`，2002/2003/2006/2013 等 → `UPSTREAM_UNAVAILABLE` |
| Mongo | ping/collections/find/aggregate/stats 的 catch-all 改为 `classify.mongo_error`：code 13/18 → AUTH，2/9/14/27/72/73/121/168 → QUERY，50/7 → TIMEOUT，ServerSelection/ConnectionFailure → UNAVAILABLE |
| Elasticsearch | `base.check_http_response`：401/403 → AUTH，400/422 → QUERY，404 → NOT_FOUND（保持），5xx/429 → UNAVAILABLE；`es.py::_request` 不再把 QUERY/AUTH 错误吞成「所有 host 均不可用」 |
| Redis | `_run` 的 catch-all 改为 `classify.redis_error`：NOAUTH/WRONGPASS/AuthenticationError → AUTH，ResponseError（WRONGTYPE 等）→ QUERY，ConnectionError → UNAVAILABLE，TimeoutError → TIMEOUT；HELLO/RESP3 专门提示保持 |
| 日志 | `log.py::_UPSTREAM` 加入两码，按 `upstream.error` 记录、不打印 traceback |
| 展示 | `web/labels.py`：`UPSTREAM_UNAVAILABLE` →「上游不可达」，新增「上游拒绝查询」「上游认证失败」；`en.json` 同步英文（upstream unreachable / upstream rejected the query / upstream authentication failed） |
| 文档 | `planning.md` 8.2 错误码表补充两码的「场景」与「模型侧建议」 |

## 验证

- 新增 `tests/test_connectors_classify.py`：MySQL 1054/1064/1146/1045/1044/2003/1205、SQLSTATE 兜底；Mongo 13/2/50/ServerSelection；Redis WRONGTYPE/NOAUTH/AuthenticationError/ConnectionError/TimeoutError；ES 400/401/403/429/500；`code_for` 两码映射。
- `tests/test_connectors_base.py`：HTTP 状态映射更新（401/403→AUTH，400→QUERY，429→UNAVAILABLE）。
- `tests/test_errors.py` / `test_labels.py` / `test_audit_page.py` 更新两码与「上游不可达」标签断言。
- 全量 `pytest`：538 passed, 1 failed（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）；`ruff check .` 全过。
- 截图（测试客户端渲染审计弹层，Chrome 156）：
  - [UPSTREAM_QUERY_ERROR（上游拒绝查询）+ 上游原文](assets/ui/audit-upstream-query-error-1440.webp)

## 边界

- MCP 契约只**新增**两码，不重命名老码；`UPSTREAM_UNAVAILABLE` 语义收窄为连接/中断/5xx/连接数满。
- 历史审计不回填：旧行仍是旧码；其中个别旧行（如之前 1054 那条）现在会显示「上游不可达」+ 原文错误详情，属于已知不一致，按决定不迁移。
- 锁等待 1205/1213 与网络超时归 `UPSTREAM_TIMEOUT`；限流/连接数满归 `UPSTREAM_UNAVAILABLE`；未新增 `UPSTREAM_BUSY`。
- 分类器按驱动异常的 errno/code/类名做鸭子类型判断，未对真实上游逐项造故障验证；真实数据只覆盖了 MySQL 1054 这一类（来自审计记录）。
- 无数据库迁移；错误码是字符串。**需要重启服务生效**。
