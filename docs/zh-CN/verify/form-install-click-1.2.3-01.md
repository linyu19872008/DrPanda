# 表单“安装客户端”点击无请求修复 1.2.3 · 验证记录

## 现象

1.2.2 页面已显示：

```text
连接测试失败
mongo client is not installed
[安装客户端]
```

点击按钮没有网络请求，也没有任何提示。

## 根因

`app.js` 中错误地从外部隐藏表单查找按钮：

```js
const installButton = installForm
  ? installForm.querySelector("[data-probe-install-button]")
  : null;
```

实际 DOM：

```text
主表单 form[data-target-form]
  └── 安装按钮 data-probe-install-button

外部表单 form[data-probe-install-form]
  └── 只有 _csrf/type/target_id 隐藏字段
```

所以 `installButton` 永远是 `null`，`doInstall()`：

```js
if (busy || !installForm || !installButton) return;
```

直接静默返回，没有发出 `/targets/install-client`。

## 修复

从主表单查找按钮：

```js
const installButton = form.querySelector("[data-probe-install-button]");
```

## 验证

- 新增 `tests/test_web_assets.py` 静态回归测试，锁定按钮必须从主表单查找；
- 全量测试：**579 passed**；
- `ruff check .`：通过；
- `node --check app.js`：通过；
- 文档链接检查：通过；
- `uv build --offline`：成功生成 `dr_panda_mcp-1.2.3` sdist/wheel。

## 发布

- 版本：1.2.3；
- 修复表单安装按钮的 JS 作用域错误，不涉及后端接口或数据库。
