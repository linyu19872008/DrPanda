# Redis RESP2 兼容 01 · 验证记录

背景：网页「连接测试」报 `redis 读取失败：unknown command 'HELLO'`。根因是 `redis-py`
8.1.0 从 8.0 起默认在链路上使用 RESP3（`DEFAULT_RESP_VERSION = 3`），连接建立后先发
`HELLO 3`；Redis < 6.0 与 Codis/Twemproxy 等只实现 RESP2 的代理不认该命令，而连接器没有
显式指定 `protocol`，完全跟随库默认值。Docker 联调用的是 redis:7.2（支持 HELLO），所以
该兼容问题一直未暴露。

本记录对应 P0（固定 RESP2）、P1（target 级协议选项）、P2（HELLO 友好错误）三项。

## 变更

| 项 | 现状 |
|---|---|
| P0 协议默认 | `connectors/redis.py` 的 `_client()` 显式传 `protocol`，不再跟随 redis-py 默认值；缺省解析为 2 |
| P1 target 选项 | 新增 `options.protocol`（2/3，默认 2）：`_protocol()` 解析并校验，只接受 2/3，非法值返回 `UPSTREAM_UNAVAILABLE`；web 表单新增「协议版本（RESP）」下拉（默认 2），并补 en 翻译 |
| P2 友好错误 | `_run()` 识别服务端 `unknown command 'HELLO'`，返回带指引的 `UPSTREAM_UNAVAILABLE`：「服务端可能是 Redis < 6.0 或代理型 Redis，请把该目标的『协议版本』改回 2」；其他异常仍保留 `redis 读取失败：` 前缀 |
| 文档 | `docs/planning.md` Redis 字段表新增协议版本行，并补充协议说明 |

## 验证

- 单测（`tests/test_connectors_data.py`）：
  - `test_redis_client_protocol`：未配置/`"2"`/`"3"` 三种情况分别传 `protocol=2/2/3`
  - `test_redis_client_rejects_invalid_protocol`：`"4"`/`"resp2"`/`"abc"` 抛 `UPSTREAM_UNAVAILABLE` 且不构造客户端
  - `test_redis_hello_error_gets_resp2_hint`：`unknown command 'HELLO'` 得到指引文案
  - `test_redis_other_errors_keep_wrapped_prefix`：普通异常仍是 `redis 读取失败：…`
- 表单：`parse_form` 默认值 2、`"3"` 正常入库、`"4"` 被选择项校验拦下；en 文案可翻译。
- 端到端（真实连接器 + 只支持 RESP2 的假服务端）：
  - 默认 / 显式 `protocol=2`：服务端只收到 `CLIENT SETINFO` 与 `PING`，探测成功
  - 显式 `protocol=3`：服务端收到 `HELLO 3` 并被拒，连接器返回可读指引，而非原始 `unknown command` 直出
- `ruff check .`：全过。
- 全量 `pytest`：525 passed, 1 failed；唯一失败是 `tests/test_healthz.py::test_mcp_route_mounted`
  （`SecurityHeadersMiddleware` 无 `routes` 属性），已在干净 HEAD 上复现，属既有问题，与本次无关。

## 边界

- RESP3 是 target 级显式选择；服务端需 Redis ≥ 6.0 且没有只认 RESP2 的代理，否则 P2 的提示会引导改回 2。
- Redis 6+ 的 ACL 用户名认证在 RESP2 下通过 `AUTH username password` 完成；Redis < 6.0 不支持 ACL 用户名。
- 本次未重跑 Docker 联调；真实老版本/代理型 Redis 的连通性以修复后线上目标测试为准。
