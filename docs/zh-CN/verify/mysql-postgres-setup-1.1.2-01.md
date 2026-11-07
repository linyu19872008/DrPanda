# MySQL / PostgreSQL 真实安装验证 1.1.2 · 验证记录

## 背景

1.1.1 修复了 MySQL 保留字 `key` 后，真实 MySQL 安装继续在迁移 0007 失败：

```text
alembic.util.exc.CommandError:
All MySQL CHANGE/MODIFY COLUMN operations require the existing type.
```

原因是 `batch.alter_column("environment_id", nullable=False)` 在 MySQL 上会生成 `MODIFY COLUMN`，必须提供现有列类型。

## 修复

[0007_environments.py](../../../src/dr_panda_mcp/store/alembic/versions/0007_environments.py) 的 `batch.alter_column` 增加：

```python
existing_type=sa.BigInteger().with_variant(sa.Integer, "sqlite"),
existing_nullable=True,
```

## 真实数据库验证

本机使用 Docker 启动：

```text
MySQL 8.0.36
PostgreSQL 16
```

通过新增脚本：

```bash
DR_PANDA_TEST_MYSQL_URL=... \
DR_PANDA_TEST_POSTGRES_URL=... \
python scripts/integration/check_db_setup.py
```

验证内容：

- 从空测试库开始；
- 完整 SetupApp HTTP 流程：
  - `/setup/admin` 设置管理员；
  - `/setup/database` 测试连接；
  - `action=finish` 完成安装；
  - `/healthz`、`/`、`/targets`、`/settings`、`/audit`、`/me` 返回 200；
- 检查 `alembic_version=0013_capacity_settings`；
- 检查默认环境 `Default`；
- 检查 admin 用户存在；
- 再次执行 `migrate(engine)`，确认幂等。

结果：

```text
OK mysql: full setup, pages, schema and idempotent migration
OK postgresql: full setup, pages, schema and idempotent migration
```

## 回归测试

- `pytest -q`：570 passed；
- `ruff check .`：通过；
- `uv build --offline`：成功生成 `dr_panda_mcp-1.1.2` wheel/sdist；
- 新增 `.github/workflows/ci.yml` 的 `database` job：
  - MySQL 8.0 service container；
  - PostgreSQL 16 service container；
  - 运行同一套完整安装脚本。

## 发布

- 版本：1.1.2；
- MySQL/PostgreSQL 首次安装修复；
- 已失败的 MySQL 库仍需清库或移除半迁移表，不能直接 stamp 0007。
