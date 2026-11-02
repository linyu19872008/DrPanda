# SQLite WAL 可见性收口

## 现象

SQLite 配置库使用 WAL 模式。主文件在未 checkpoint 时可能只有 4KB、`schema=0`，表和迁移记录都在 `dr-panda.sqlite-wal` 中。SQLite 自身连接能自动读到，但部分外部查看器只打开主文件，显示“没有可用的表”。

这与数据库损坏无关，也不是迁移没执行。

## 实现调整

- 迁移完成后、应用开始服务前执行一次：
  ```sql
  PRAGMA wal_checkpoint(TRUNCATE)
  ```
- 正常关闭时、`engine.dispose()` 前再执行一次。
- 非 SQLite/内存库跳过；checkpoint 失败只记日志，不阻断启动或关闭。
- 保持 WAL 模式不变，继续保留并发读写收益。

实现位置：[store/url.py](../../src/dr_panda_mcp/store/url.py) / [runtime.py](../../src/dr_panda_mcp/runtime.py)。

## 验证

- 新增 `tests/test_sqlite_wal.py`：
  - 启动后只复制主文件（不带 WAL）也能看到 `targets/audit/settings/alembic_version`；
  - 写入审计后正常关闭，只复制主文件也能读到该审计。
- 全量 `pytest`：**431 passed**；`ruff` 通过。

## 外部查看器使用说明

- 应用运行中查看：打开 `data/` 目录下的主库，并确保同一目录的 `-wal`、`-shm` 可读；或用 SQLite 连接后先执行 `PRAGMA wal_checkpoint(TRUNCATE)`。
- 复制/备份：不要只 `cp dr-panda.sqlite`；使用项目已有的 `sqlite3.Connection.backup` 备份（`backup_sqlite_database`）。
- 应用正常关闭后，主文件已 checkpoint，通常可直接被查看器打开。

## 仍未改

- 不切换 `journal_mode=DELETE`；如果未来外部工具兼容性优先于 WAL 并发收益，再单独评估。
- 强杀进程（SIGKILL）无法保证关闭 checkpoint；WAL 恢复由 SQLite 下次打开处理。
