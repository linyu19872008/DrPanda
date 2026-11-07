# gzip 响应重复解压修复 1.2.4 · 验证记录

## 现象

Elasticsearch 连接测试显示：

```text
all elasticsearch hosts are unavailable:
Error -3 while decompressing data: incorrect header check
```

## 根因

`stream_http()` 使用：

```python
async for chunk in response.aiter_bytes():
```

读取时，httpx 已经自动解压了 gzip/br 等响应。随后代码重新构造：

```python
httpx.Response(
    response.status_code,
    headers=response.headers,
    content=content,
    request=response.request,
)
```

原 headers 仍带：

```text
Content-Encoding: gzip
```

httpx 于是对已解压的正文再次解压，抛出：

```text
Error -3 while decompressing data: incorrect header check
```

这是通用连接器问题，不是 Elasticsearch 配置问题；所有使用 `stream_http()` 的 HTTP 上游都可能受影响。

## 修复

重建响应时移除已被处理的传输头：

- `content-encoding`
- `content-length`
- `transfer-encoding`

保留 `content-type`、状态码、已解码正文和 request 信息。httpx 会按解码后的正文重新计算 Content-Length。

## 验证

新增测试：

1. `stream_http` 接收 gzip 响应：
   - 只解压一次；
   - `.json()` 正常；
   - 不再包含 `content-encoding`；
   - Content-Length 对应解码后正文。
2. 未压缩响应保持兼容。
3. Elasticsearch `_ESClient.ping()` 接收 gzip `_cluster/health` 成功。

全量验证：

- `pytest -q`：**582 passed**；
- `ruff check .`：通过；
- `node --check app.js`：通过；
- 文档链接检查：通过；
- `uv build --offline`：成功生成 `dr_panda_mcp-1.2.4` sdist/wheel。

## 发布

- 版本：1.2.4；
- 修复通用 HTTP gzip 响应处理，不涉及数据库或 Web 路由行为变更。
