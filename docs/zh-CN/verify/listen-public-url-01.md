# 监听地址与 PUBLIC_URL 语义调整 01 · 验证记录

背景：确认采用「HOST 作为唯一暴露开关」的方案：去掉 `DR_PANDA_ALLOW_REMOTE`，`DR_PANDA_PUBLIC_URL`
改为纯展示，新增 Cookie Secure 策略与 MCP Host 白名单两个可选变量；保留首次安装必须 loopback。

## 变更

| 层 | 改动 |
|---|---|
| 配置 | `config.py`：删除 `allow_remote`；新增 `DR_PANDA_COOKIE_SECURE`（`auto`/`always`/`never`，默认 `auto`）和 `DR_PANDA_TRUSTED_HOSTS`（逗号分隔）；`PUBLIC_URL` 只保留展示语义 |
| 启动 | `__init__.py`：非 loopback 不再要求 `ALLOW_REMOTE`/HTTPS `PUBLIC_URL`，启动时输出警告日志；首次安装必须 loopback 的限制保留 |
| Cookie | `auth.py` 新增 `cookie_secure_required(policy, scheme)`；登录、页面续期、安装完成页统一按策略设置 Secure；`AuthMiddleware` 把策略放入 `request.state` |
| MCP | `server.py`：`PUBLIC_URL` 不再参与 Cookie 或 Host/Origin 白名单；`allowed_hosts` 只来自 `TRUSTED_HOSTS`（未设置时交给 FastMCP 默认策略） |
| 地址展示 | `profile.py`：`PUBLIC_URL` 优先，否则按当前请求的 scheme/Host 推导；不再把 `0.0.0.0` 强行替换成 `127.0.0.1`。安装完成页同样优先展示 `PUBLIC_URL` |
| 页面 | 启动配置只读区去掉「允许远程监听」；「公网地址」标注「仅展示」；新增「Cookie Secure」「受信 Host」 |
| 文档 | README、planning、ui-design、`.env.example` 同步新语义 |

## 行为矩阵

| 场景 | 现在的行为 |
|---|---|
| 本机默认 | `127.0.0.1:8111`，零配置；Cookie 按请求 scheme（http 不加 Secure） |
| 服务器直接 `HOST=0.0.0.0` | 安装完成后可直接监听所有网卡；不再要求 `ALLOW_REMOTE`；启动日志提示建议 HTTPS 反代 |
| 服务器 + HTTPS 反向代理 | 建议 `COOKIE_SECURE="auto"`；跨机反代需设置 uvicorn 的 `FORWARDED_ALLOW_IPS`，否则应用侧看到的 scheme 可能是 http |
| 需要 `/mcp` Host 白名单 | 设置 `DR_PANDA_TRUSTED_HOSTS="mcp.example.com"`；不设时 loopback 自动保护，wildcard 绑定不启用显式白名单 |
| `PUBLIC_URL` | 只影响页面/复制出来的 MCP 地址；写错不再影响 Cookie 或 Host 校验，也不会阻止启动 |
| 首次安装 | 仍必须在 loopback 完成，防止远程抢注管理员 |

## 验证

- 新增/更新测试：
  - `test_config.py`：Cookie Secure/Trusted Hosts 解析与非法值、`cookie_secure_required` 策略；
  - `test_startup.py`：非 loopback 且未安装时仍拒绝启动（保留首次安装护栏）；
  - `test_web_async.py`：`COOKIE_SECURE="never"` 时登录 Cookie 不带 Secure；
  - `test_web.py`：启动配置页新增字段的英文全覆盖仍通过。
- 全量 `pytest`：**554 passed, 1 failed**（既有的 `test_healthz.py::test_mcp_route_mounted`，与本次无关）；`ruff check .` 全过。
- 截图（测试客户端渲染启动配置 + Chrome 156）：
  - [启动配置：公网地址仅展示、Cookie Secure、受信 Host](assets/ui/settings-startup-v2-1440.webp)

## 边界与风险

- 非 loopback 不再强制 HTTPS，也不再要求额外确认；管理台/MCP Token 在明文 HTTP 下传输的风险由部署方承担，建议始终通过 HTTPS 反向代理访问。
- `COOKIE_SECURE=auto` 依赖请求 scheme；反向代理在另一台机器时需配置 `FORWARDED_ALLOW_IPS`，否则 Cookie 可能不带 Secure（仍能登录，但保护变弱）。
- 未配置 `TRUSTED_HOSTS` 时，`0.0.0.0` 绑定下 `/mcp` 没有显式 Host/Origin 白名单（FastMCP auto 行为）；对公网部署建议显式配置。
- 环境变量 `DR_PANDA_ALLOW_REMOTE` 已不再读取，旧部署里保留该变量不会报错也不会生效。
- `PUBLIC_URL` 为空时 MCP 地址按当前请求推导；反向代理若未正确传 Host/Proto，展示出来的地址可能不准确（只影响展示与复制）。
- 无数据库迁移；改这些变量需要**重启服务**生效。页面编辑监听地址/端口仍未实现（按之前讨论保持现状）。
