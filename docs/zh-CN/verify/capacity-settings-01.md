# 资源类系统配置 01 · 验证记录

背景：系统配置升级后，继续落地 P2 的「资源类」配置：全局并发上限、连接器空闲回收、审计清理
批量与时限。日志级别因设置模型只支持整数（需要枚举/字符串类型改造）、页面条数类配置价值低，
本轮不做，留作后续。

## 变更

| 新配置 | 默认/范围 | 生效方式与实现 |
|---|---|---|
| `global_max_concurrent_calls` | 0（不限）/ 0–200 | `Catalog.slot()` 在每 target 信号量外再叠加一个全局信号量；设置变化时重建；下一次取槽生效，已在跑的调用不取消 |
| `catalog_idle_seconds` | 0（不回收）/ 0–3600 | `_Pooled` 记录 `last_used`；`_evict_if_needed()` 先回收超时未使用的连接，再按缓存上限淘汰；下一次取客户端生效 |
| `audit_cleanup_batch_size` | 1000 / 100–5000 | `audit.cleanup_once()` 读取配置并传给 `cleanup_audit(batch_size=...)`；下一轮清理生效 |
| `audit_cleanup_max_seconds` | 300 / 10–3600 | 同上，作为单轮清理时限；达到时限后剩余记录留到下一轮 |

其它：
- 迁移 `0013_capacity_settings` 写入 4 行配置（settings 共 17 行）；
- `settings.py` specs/加载、`Settings` 数据类、`en.json` 翻译、README/planning/ui-design 文档同步；
- 审计清理间隔帮助文案更新为「分片检查，改小最多 60 秒内生效」。

## 验证

- 新增测试：
  - `test_catalog.py`：全局并发上限（3 个 target 并发 9 次，`max_active <= 2`）；空闲回收（时钟推进 11 秒后旧连接被关闭）；缓存上限调小后命中缓存即淘汰。
  - `test_audit_cleanup.py`：清理批量/时限按配置传入；间隔分片睡眠 1 分钟内按新值结束。
  - `test_settings.py`：新配置范围校验（global 201、idle 3601、batch 99、time 9 拒绝）。
  - `test_migrate.py` / `test_store_contract.py` / `test_web.py`：settings 行数、默认值、英文页面同步更新。
- 全量 `pytest`：**549 passed, 1 failed**（既有的 `test_healthz.py::test_mcp_route_mounted`，与本次无关）；`ruff check .` 全过。
- 迁移在**真实数据副本**上验证：从当前线上库版本 `0012_security_settings` 升级到
  `0013_capacity_settings`，settings 共 17 行；`default_target_max_rows=1000` 与审计数据保留；
  `backup_keep_count` 上限仍为 100。
- 截图（测试客户端渲染 + Chrome 156）：
  - [并发与审计：全局并发、审计清理批量/时限](assets/ui/settings-runtime-p2-1440.webp)
  - [高级资源：连接器空闲回收](assets/ui/settings-advanced-p2-1440.webp)

## 边界

- 全局并发 0 表示不限制；设置变化时新建信号量，已在跑的调用继续执行到结束。
- 空闲回收只在取客户端时检查，不做后台定时清理；0 表示关闭。
- 审计清理批量/时限在下一次清理周期读取；清理仍不写审计、只记日志。
- 日志级别运行时调整、页面条数类配置本轮未做。
- 无回填迁移；需要**重启服务**（启动时自动执行 0013 并备份 SQLite）。
