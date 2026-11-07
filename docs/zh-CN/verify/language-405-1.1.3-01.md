# 登录页语言切换 405 修复 1.1.3 · 验证记录

## 现象

登录成功后日志出现：

```text
POST /login 200
GET /language 405 actor=admin
```

登录页语言按钮点击时产生：

```text
POST /language 303
GET /login 200
```

## 根因

- 登录页也渲染了顶部语言/主题切换表单；
- `/language`、`/theme` 不在 `PUBLIC_PATHS` 中；
- 未登录 POST `/language` 被 AuthMiddleware 拦截，重定向到 `/login?next=%2Flanguage`；
- 登录表单保留 `next=/language`；
- 登录成功后浏览器 GET `/language`，但该路由只接受 POST，因此 405。

`/theme` 存在同样问题。

## 修复

1. `web/security.py`
   - `/language`、`/theme` 加入 `PUBLIC_PATHS`；
   - 这两个路由只改 Cookie，仍受 CSRF 校验。

2. `web/theme.py`
   - `safe_next` 拒绝 `/language`、`/theme` 这类 POST-only 落点。

3. `web/security.py`
   - 未登录时只有 GET 请求保留 `next`；
   - 非 GET 请求登录后落点归一化为 `/`，避免把 POST 路径当成 GET 页面。

## 测试

新增：

- 未登录带 CSRF 请求 `POST /language`：303、Cookie 更新、回到 `/login`；
- 未登录带 CSRF 请求 `POST /theme`：303、Cookie 更新、回到 `/login`；
- 登录页 `next=/language` 登录后落点为 `/`；
- 未登录 POST 受保护路径不再把 POST 路径写入 `next`；
- `safe_next("/language")` / `safe_next("/theme")` 返回 `/`。

验证：

- `pytest -q`：**573 passed**；
- `ruff check .`：通过；
- 文档链接检查：通过；
- `uv build --offline`：成功生成 `dr_panda_mcp-1.1.3` sdist/wheel。

## 发布

- 版本：1.1.3；
- 仅修复 Web 登录页语言/主题与登录落点，不涉及数据库迁移或运行时 API。
