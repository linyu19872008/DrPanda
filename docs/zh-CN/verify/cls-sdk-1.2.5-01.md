# CLS SDK 构造兼容修复 1.2.5 · 验证记录

## 现象

CLS 新建目标测试连接显示：

```text
未预期错误: AbstractClient.__init__() got an unexpected keyword argument 'timeout'
```

## 根因

代码把 `timeout` 传给了 Tencent SDK 的 `ClsClient`：

```python
ClsClient(credential, region, timeout=...)
```

但当前 SDK 的构造签名是：

```python
AbstractClient.__init__(credential, region, profile=None)
```

超时应该通过 `HttpProfile.reqTimeout` 设置。

## 修复

- 使用 `HttpProfile(reqTimeout=...)` 和 `ClientProfile(httpProfile=...)`；
- `ClsClient(credential, region, profile)`；
- `_sdk()` 的构造错误被包装为 `UpstreamUnavailable`，错误信息保留异常类型和原因；
- 表单地域字段增加示例提示：`ap-shanghai`。

## 兼容性

- 不依赖 SDK 是否接受 `timeout` 关键字；
- 使用 Tencent SDK 稳定的 `HttpProfile` / `ClientProfile` 接口；
- 当前 CI 安装 `--all-extras`，覆盖 CLS 依赖。

## 验证

新增测试：

- 使用真实安装的 Tencent SDK 构造 `_CLSClient._sdk()`；
- 断言 `client.profile.httpProfile.reqTimeout` 等于 target 超时；
- 断言地域正确传入。

全量验证：

- `pytest -q`：**583 passed**；
- `ruff check .`：通过；
- `node --check app.js`：通过；
- `bash -n setup.sh`：通过；
- 文档链接检查：通过；
- `uv build --offline`：成功生成 `dr_panda_mcp-1.2.5` sdist/wheel。

## 发布

- 版本：1.2.5；
- 修复 CLS 客户端构造，不涉及数据库或 Web 路由行为变更。
