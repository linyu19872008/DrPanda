# 异步交互与保存门槛（frontend-js-policy v2）

## 背景

审计发现「测试连接」按钮实际执行的是「保存」：

- `app.js` 在 `submit` 事件里禁用表单内所有 `button[type=submit]`，包括刚被点击的提交按钮；
- 表单数据在 `submit` 之后构造，被禁用的按钮不再算提交按钮，`name=action&value=test` 从请求体消失；
- 服务端 `form.get("action")` 为空 → 走保存分支（新建/编辑目标直接落库）；
- 同一个缺陷也让安装向导的「完成安装」（`action=finish`）退化为“再测一次”，安装无法完成。

真实 Chrome 156（CDP）复现：修复前 POST body 只有 `name=mongo-x`；加 submitter 镜像隐藏域后为 `name=mongo-x&action=test`。

同时确认了约束前提问题：`docs/zh-CN/verify/frontend-js-policy.md` 原来禁止“脚本发额外网络请求”，导致探测/保存只能整页重渲染。v2 允许同源 fetch，改为“服务端为准 + 前端体验”。

## 改造内容

### 服务端

- 新增 `web/async_api.py`：`Accept: application/json` 识别、统一 JSON 信封（`ok/code/message/errors/phase/redirect`）、`no-store`、按请求语言翻译。
- `web/security.py`：未登录的 JSON 请求返回 401 JSON（带 `login` 跳转）；CSRF 失败返回 403 JSON；新增全局 `SecurityHeadersMiddleware`（CSP、nosniff、DENY、Referrer-Policy）。
- `web/routes.py`：
  - 新增 `POST /targets/probe`、`POST /targets/{id}/probe`：只做只读探测，不写库、不写审计；
  - 新建/编辑保存前**必须**完成一次真实探测，失败返回 400 且不落库；成功后写库并把测试结果写回 `last_test_*`；
  - 列表测试/启停、系统配置保存返回 JSON（含行内展示字段与统计）；
  - `require(probe_guard())` 移入 `try`，闸门拒绝不再 500。
- `web/auth_routes.py`、`web/profile.py`、`setup.py`：登录、改密、安装向导测试/完成安装支持 JSON 形态；安装向导与正常应用共用安全响应头。
- `web/forms.py`：授权范围字段标记为不参与保存门槛（`gate=False`）。
- `web/assets.py`：`app.js` 版本号按内容哈希自动破缓存（无需手工处理）。

### 前端

- `app.js`：
  - submitter 镜像修复（保住 `action` 语义，同时保留防重复提交）；
  - 同源 fetch 底座：urlencoded 请求体（沿用双提交 Cookie CSRF）、`Accept: application/json`、`AbortController` 超时、401 跳登录、403/网络/超时错误归一；
  - 目标表单保存门槛：默认置灰 → 探测成功后解禁 → 门槛字段变化重新置灰（改回已测快照可恢复）；
  - 结果区内联展示（成功/失败/耗时/时间），失败原因脱敏；
  - 列表行内测试/启停：只更新当前行与统计，不整页刷新；
  - 系统配置保存、登录、修改密码、安装向导：内联错误/成功，成功后跳转；
  - 字段错误内联回填并聚焦第一个错误；
  - 修复 `form.action` 被 `name="action"` 控件遮蔽的问题（改为读属性）；
  - 修复按钮加载态恢复时用 `textContent` 覆盖内部结构（开关被写成纯文本）。
- 模板：目标表单结果区/门槛提示/数据属性；列表行状态与统计锚点；设置/登录/改密/安装向导的结果区；`base.html` 全局错误提示与客户端文案数据属性。

## 验证

### 自动化

- 全量测试：**464 passed**（新增 `tests/test_web_async.py` 19 项 + 安装向导 JSON 用例）。
- `ruff check .`：通过。
- 覆盖：探测不写库、探测失败保存不落库、重名先于探测报错、JSON 401/403、CSP、列表/设置 JSON、登录 JSON、无 JS 保存先探测、安装向导 JSON 测试与完成安装。

### 真实 Chrome（CDP）

安装向导（无 JS 依赖的 P0 路径）：

| 步骤 | 结果 |
|---|---|
| 设置管理员密码 → 选择配置库 | 导航到 `/setup/database` |
| 点「测试连接」 | 内联 `Connection successful`，`完成安装` 解禁 |
| 点「完成安装」 | 安装完成并跳转 `/`，`install.json` 生成 |

目标表单保存门槛（GitLab 目标指向本地假上游，真实探测成功）：

| 步骤 | 结果 |
|---|---|
| 打开新建页 | 保存按钮 `disabled=true`，提示「Test the connection first」 |
| 点「测试连接」 | 结果区显示通过 + 耗时 + 时间；页面**未刷新**；保存解禁 |
| 修改 base_url | 保存重新置灰，提示「Configuration changed; test the connection again.」 |
| 改回原值 | 保存恢复可点 |
| 点保存 | 跳转 `/?flash=created`，列表出现目标，最近测试「Success」 |
| 坏地址测试连接 | 结果区显示脱敏失败原因；保存保持置灰 |

其他页面：

| 场景 | 结果 |
|---|---|
| 列表行内「测试」 | 状态/时间更新，页面未刷新 |
| 列表行内启停 | 开关状态与统计更新，页面未刷新，开关图标文字保留 |
| 系统配置保存 | 行内「Settings saved」，页面未刷新，值已保存 |
| 禁用 JS 后打开新建页 | 保存按钮可直接提交（服务端先探测再保存），测试按钮仍在 |

## 边界与未覆盖

- 探测采用“先测后存 + 保存时再测一次”的双重校验；保存耗时包含一次探测（ping / `SELECT 1` 级别）。
- Token 创建/删除、删除确认、主题/语言切换保持整页表单渲染（一次性敏感结果或需要服务端重渲染，未改为异步）。
- 多标签页各自维护自己的已测快照；在 A 页测试、B 页保存仍会触发服务端探测，不会绕过门槛。
- 未覆盖跨浏览器矩阵与真实读屏；无 JS 路径以服务端测试 + CDP 渲染检查为主。
