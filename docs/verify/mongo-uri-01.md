# Mongo URI 凭证自动转义 01 · 验证记录

背景：网页「连接测试」报 `未预期错误：Username and password must be escaped according to
RFC 3986, use urllib.parse.quote_plus`。根因是 `auth_mode=uri` 的完整连接串原样透传给
pymongo，凭证里未转义的 `@`、多余的 `:`、非法 `%` 在 `AsyncIOMotorClient()` 构造阶段就被
`pymongo.errors.InvalidURI` 拒收；该异常在 `ping()` 的 try 之外，因此以「未预期错误」直出。

本记录对应「方案 B：继续用 URI 模式，先把凭证转义」的实施——由服务端自动完成转义，
用户不需要手工编码。

## 变更

| 项 | 现状 |
|---|---|
| URI 模式凭证归一化 | `connectors/mongo.py` 新增 `_normalize_uri_credentials`：按「最后一个 `@` 前是 userinfo、userinfo 里第一个 `:` 前是用户名」重切，未转义的 `@` → `%40`、`:` → `%3A`、非法 `%` → `%25`；已有 `%XX` 原样保留，已合法 URI 完全不改（幂等） |
| 空用户名 | userinfo 为空时抛 `UPSTREAM_UNAVAILABLE`，提示正确格式 |
| 构造期异常 | `_connected()` 把 `AsyncIOMotorClient(...)` 构造异常（如 `pymongo.errors.InvalidURI`）映射为 `UPSTREAM_UNAVAILABLE("mongo 连接串无法解析：…")`，不再以「未预期错误」直出网页 |
| 表单文案 | URI 字段 help 补充「凭证里未转义的 @、:、% 会自动做 URL 编码」，并补 en 翻译 |

## 验证

- `tests/test_connectors_data.py` 新增：
  - 6 组未转义输入归一化（裸 `@`、密码含 `:`、非法 `%`、用户名含 `@`、多主机、`mongodb+srv`）
  - 4 组已合法 URI 原样返回（已转义凭证、无凭证、SRV）
  - 空用户名拒绝
  - 构造期异常映射为 `UPSTREAM_UNAVAILABLE`
- 真实 pymongo 4.19.0 手工确认：`mongodb://ro:p@ss@…` 等原先前置报 `InvalidURI` 的 URI，归一化后可正常构造客户端。
- 端到端手工确认：`mongodb://admin:p@ss:1@127.0.0.1:1/` 归一化为 `mongodb://admin:p%40ss%3A1@127.0.0.1:1/`，探测错误变为可读的 `UPSTREAM_UNAVAILABLE: mongo 探测失败：… Connection refused`，不再是「未预期错误」。

## 结果

- 全量 `pytest`：517 passed, 1 failed；唯一失败是 `tests/test_healthz.py::test_mcp_route_mounted`
  （`SecurityHeadersMiddleware` 无 `routes` 属性），已用 `git stash` 在干净 HEAD 上复现，属既有问题，与本次改动无关。
- `ruff check .`：全过。

## 边界

- 密码里 `%` 后跟合法十六进制（如 `%ab`）无法判定是「转义」还是「字面量」，按现有约定保留；若确实是字面量需用户自行写 `%25`（该形态不会报转义错，只会表现为认证失败）。
- 密码里未转义的 `/`、`?`、`#` 会先被 URI 结构切走，不在本次归一化范围，会得到主机/库名解析错误。
- X.509 / SRV / replica set 的真实连通性仍以 Docker/云环境联调为准；本次未重跑 Docker。
