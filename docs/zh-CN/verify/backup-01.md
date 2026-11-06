# SQLite 备份策略调整

## 变更

1. SQLite 备份只在存在 pending Alembic migration 时执行；普通启动不再产生新备份。
2. `BACKUP_KEEP` 默认值从 5 提高到 20。
3. 保留数量进入系统配置：`backup_keep_count`，默认 20，范围 1–20，高级资源分组，用户可在设置页调整。
4. 新增 Alembic 迁移 `0003_backup_keep`，插入配置行。

## 实现

- `migrate()` 先比较 Alembic current heads 与 script heads：
  - 有 pending：读取 `settings.backup_keep_count`，若表不存在/值非法回退 20，然后备份并 upgrade。
  - 无 pending：直接返回，不备份、不重复 upgrade。
- `backup_sqlite_database(url, keep=...)` 的 `keep` 由迁移流程传入；直接调用仍默认 20。
- 只有 SQLite 文件存在且非空才备份；MySQL/PostgreSQL 不备份。
- 旧库首次升级 0003 时，备份前读取不到该配置则使用 20，升级后配置行写入 20。

## 验证

真实库：

- 调整前：`alembic_version = 0002_settings_metadata`，settings 7 行，backup 5 个。
- 第一次启动：检测到 0003 pending，产生 1 个备份，backup 变 6 个；升级到 0003，settings 变 8 行，`backup_keep_count=20`。
- 第二次启动：无 pending，backup 仍为 6 个，没有新增。

测试：

- pending 时产生备份；
- 无 pending 时不产生备份；
- 配置值 3 时 pending 备份只保留 3 个；
- 全量 `pytest`：**444 passed**；`ruff` 通过。

## 边界

- 只有存在 pending migration 才备份；普通重启不再刷新备份。
- 已有备份不会被立即裁剪到 20，只有下一次 pending 备份时才会按新数量清理。
- 保留数量是“下一次启动迁移”生效，不是保存设置时立即裁剪。
- 首次启动空库通常因文件为空跳过备份；这是预期行为。
