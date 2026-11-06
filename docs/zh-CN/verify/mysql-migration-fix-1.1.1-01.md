# MySQL 0007 迁移修复 1.1.1 · 验证记录

## 问题

MySQL 8 首次安装执行到 Alembic `0007_environments` 时失败：

```text
(1064, "You have an error in your SQL syntax ... near 'key = 'default'' at line 1")
```

原因：`key` 是 MySQL 保留字，而迁移里用了原生 SQL：

```sql
SELECT id FROM environments WHERE key = 'default'
```

SQLite/PostgreSQL 允许这种写法，所以原有测试没有发现；只有真实 MySQL 首次迁移会暴露。

## 修复

[0007_environments.py](../../../src/dr_panda_mcp/store/alembic/versions/0007_environments.py) 不再使用原生 SQL：

- 使用 `sa.table` / `sa.column` 定义环境表；
- 使用 `sa.select(...).where(environments.c.key == "default")` 查询；
- 使用 `targets.update().values(environment_id=...)` 更新目标；
- 由 SQLAlchemy 按方言自动引用标识符：
  - MySQL：`` `key` ``
  - SQLite/PostgreSQL：`"key"` 或方言默认行为。

## 回归测试

新增 `tests/test_mysql_migration_sql.py`：

- 环境查询在 MySQL 方言下编译出 `` `key` ``；
- 环境插入在 MySQL 方言下编译出 `` `key` ``；
- 迁移源码不再包含 `WHERE key =` 的原生谓词。

验证：

- `pytest -q`：**570 passed, 0 failed**；
- `ruff check .`：通过；
- `uv build --offline`：成功生成 `dr_panda_mcp-1.1.1` sdist/wheel，METADATA `Version: 1.1.1`。

## 已失败的 MySQL 库恢复

MySQL DDL 非事务性，失败后可能留下半迁移状态：

- `environments` 表已创建；
- `alembic_version` 仍为 `0006_mcp_tokens`；
- `targets.environment_id` 尚未创建。

处理方式：

1. 首次安装、无业务数据：直接重建空库最简单；
2. 或确认 `alembic_version`、`environments`、`targets.environment_id` 状态后，只删除半成品的 `environments` 表，再用 1.1.1 重跑；
3. 不要直接 `alembic stamp 0007`。

## 发布

- 版本：1.1.1；
- 版本变更只修复 MySQL 迁移兼容性，不改变应用行为；
- 已发布 1.1.1 到 PyPI：<https://pypi.org/project/dr-panda-mcp/1.1.1/>；
- README PyPI 徽标 cache 参数更新为 `?cache=1.1.1`；
- 发布后新 MySQL 安装使用修复后的 0007。
