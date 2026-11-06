# 前端 JavaScript 约束（v3）

## 这次调整

v0.32 允许本地脚本做 dialog 和复制。v0.36 允许同源 fetch。v0.37 取消「核心流程无 JS 仍可用」：

- 同一套 POST 既返回整页 HTML 又当交互协议，把测试和保存焊在同一个提交按钮上，点测试会变成保存；
- 为无 JS 再做一套确认页和按钮，对话框里的信息和独立页面不一致；
- 这条约束没有换来安全。认证、CSRF、Host/Origin、字段校验、只读闸门本来就在服务端。

配置台现在要求启用 JavaScript。`<noscript>` 只提示一句。非 JSON 的 POST 仍可返回 303 或 HTML，给测试和直接请求用；浏览器里的按钮只发 `Accept: application/json`。

以下两条不变：

1. **服务端是唯一事实来源**：认证、权限、CSRF、Host/Origin、字段校验、只读闸门、连接探测都由服务端执行。
2. **不出现假按钮**：失败要如实提示，不能显示“能点但没反应”的功能。

## 规则

### 必须保持

- Jinja2 服务端渲染。首屏语言和主题由服务端输出。
- 不引入 React/Vue/Next，不引入 npm 构建链，不引入外部 CDN、字体、第三方脚本。
- 服务端对 JSON 请求与普通表单请求执行同一套校验。
- 不在 localStorage / sessionStorage / URL / 日志里保存 Token、密钥或连接串。
- 请求只允许同源，并携带 CSRF。
- JSON 响应 `Cache-Control: no-store`；信封为 `{ok, code, message, errors, phase, redirect}`。
- 安全响应头保持 `script-src 'self'`、`connect-src 'self'`。模板不写内联脚本。

### 交互

- 文档页用 GET：列表、类型选择、新建/编辑、设置分组、登录、安装、账号。
- 命令用 POST + `Accept: application/json`：测试、保存、启停、删除、设置、密码、Token、主题。
- 只有登录成功、创建完成、删除完成跟随 `redirect`。设置保存、测试失败、校验失败留在当前页。
- 主题立即改 `data-theme` 再 POST，不整页刷新。语言仍整页加载；未保存表单先确认。
- 测试连接是 `type="button"`。保存是唯一的提交按钮。不要靠提交按钮的 name/value 区分动作，也不要在原生 submit 里禁用那个提交按钮。

### 保存前探测

- 新建必须探测成功才写入。
- 编辑只在主机、端口、账号、密钥、URI、TLS/SSL、超时变化时探测。授权范围、启停、行数、字节上限直接保存。
- 跳过探测时不要把最近测试记成成功。

## 当前 JS 资产

| 文件 | 用途 |
|---|---|
| `web/static/app.js` | JSON 命令、dialog、保存门槛、行内测试/启停、主题、离开确认 |
| `web/static/copy-token.js` | 复制一次性 MCP Token |

## 验证

- JSON 契约、探测接口、编辑时跳过探测，见 `tests/test_web_async.py`、`tests/test_web.py`。
- 浏览器需要覆盖：新建先测试再保存、编辑只改范围可直接保存、主题不刷新、设置保存留在当前分组。
