# 前端 JavaScript 约束调整

## 背景

项目早期采用“严格零客户端 JavaScript”。该约束降低了前端工程与供应链复杂度，但也被证明过度：

- 浏览器剪贴板必须使用 JS；
- 纯 CSS `:target` 弹窗没有 Esc、焦点陷阱等原生行为；
- 为绕开 JS 容易产生整页跳转、URL hash 状态和不自然的交互。

因此改为：

> **服务端优先；禁止前端框架、构建链、第三方脚本；JavaScript 仅做局部渐进增强。**

## 规则

### 必须保持

- Jinja2 服务端渲染；
- 所有核心流程在无 JS 时可用；
- 登录、目标增删改、系统配置、Token 创建/删除的基线使用普通表单；
- 不引入 React/Vue/Next 等框架；
- 不引入 npm/Node 构建链；
- 不引入外部 CDN、字体、第三方脚本；
- 不把 Token、密钥写日志、URL 或 localStorage；
- 脚本只操作本页 DOM，不发额外网络请求。

### 允许

- 自托管、无依赖、小体积静态 JS；
- 渐进增强：
  - `app.js`：原生 `<dialog>` 打开/关闭、Esc/焦点行为、结果弹窗；
  - `copy-token.js`：Token 复制按钮；
- 无 JS 时回退到普通页面或可全选 Token + 快捷键提示；
- 脚本加载失败时不显示不可用的按钮。

### 禁止

- 用脚本改写核心认证、CSRF、Host/Origin 校验；
- 用前端状态代替服务端校验；
- 在脚本中记录 Token 或凭据；
- 把 Token 放入 URL/query/hash；
- 通过第三方 CDN 加载脚本；
- 为了动画/视觉引入大型运行时。

## 当前 JS 资产

| 文件 | 用途 | 加载范围 | 无 JS 行为 |
|---|---|---|---|
| `web/static/app.js` | 原生 dialog 打开/关闭 | `/me` | 链接进入回退表单/确认页 |
| `web/static/copy-token.js` | 复制 Token | Token 结果页 | 按钮隐藏；显示全选 + ⌘C/Ctrl+C 提示 |

## 无 JS 回退

- 生成 Token：`/me/tokens/new` 独立表单；
- 删除 Token：`/me/tokens/{id}/delete` 独立确认页；
- 创建结果页：`<dialog open>` 直接显示 Token，复制按钮隐藏；
- 所有表单仍由服务端校验和 CSRF 保护。

## 验证

- 核心页面无脚本可用；
- `/me` 使用原生 dialog；真实 Chrome 验证 Esc/焦点/遮罩；
- 复制按钮真实写入剪贴板；权限拒绝时选中文本并提示，不谎报成功；
- 无 JS 回退页可用；
- 脚本静态资源 200；
- 全量测试 **444 passed**，`ruff` 通过。
