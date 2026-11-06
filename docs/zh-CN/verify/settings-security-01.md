# 系统配置升级 01 · 验证记录

背景：只读盘点 9 个系统配置项后确认 3 处生效性/治理问题，并按确认的方案补充安全类配置。
本轮落地：3 处修正 + 4 个新配置（Token 上限/有效期、登录失败保护）+ 备份保留上限放宽 +
启动配置只读区补字段。

## 变更

### 1. 三处修正

| 问题 | 改动 |
|---|---|
| `catalog_max_clients` 降低后，缓存命中路径提前返回、不触发淘汰 | `catalog.client()` 命中缓存后也执行 `_evict_if_needed()`；下次取客户端即生效 |
| `audit_cleanup_interval_minutes` 改小要等当前整段 sleep（最坏 24h） | 改为 60 秒分片睡眠，每片重新读取配置；改小最多一分钟生效，改大从当前轮继续 |
| 保存/恢复配置把未变化的键也写 history/audit（旧库有 3 条 no-op 记录） | `update_settings` 只对实际变化的键写 `settings_history` 与 `settings_update` 审计；无变化不写审计 |

### 2. 新增安全类配置（迁移 0012）

| 新键 | 默认/范围 | 生效与实现 |
|---|---|---|
| `login_max_attempts` | 5 / 1–50 | 登录路由按来源 IP 统计失败次数；达到后在锁定时长内返回 429 |
| `login_lockout_minutes` | 5 / 1–1440 | 失败计数窗口与拒绝时长；成功登录清空计数 |
| `mcp_token_max_per_user` | 5 / 1–50 | `/me/tokens` 创建前校验数量，达到上限返回 400 提示先删除旧 Token |
| `mcp_token_ttl_days` | 0（不过期）/ 0–3650 | MCP Bearer 认证时按 Token 创建时间校验；过期返回 401 |

- `backup_keep_count` 范围 1–20 → **1–100**，`migrate._configured_backup_keep` 同步放宽到 100。
- `Settings` 数据类、`settings.py` specs/加载、迁移种子、页面分组、英文文案同步更新。

### 3. 启动配置只读区

新增「公网地址」「允许远程监听」两行（来自 `DR_PANDA_PUBLIC_URL` / `DR_PANDA_ALLOW_REMOTE`）；
启动配置值也走翻译（英文页面不再残留中文「未设置 / 允许 / 不允许」）。

## 验证

- 新增/更新测试：
  - `test_store_contract.py`：no-op 保存不写 history/audit；部分 patch 只记录变化键。
  - `test_catalog.py`：上限调小后，缓存命中也会淘汰到新上限。
  - `test_audit_cleanup.py`：分片睡眠在配置改小后 1 分钟内结束。
  - `test_m7.py`：Token 数量上限、Token 过期后 MCP 请求 401。
  - `test_web_async.py`：登录失败次数/锁定时长随配置变化（2 次失败后 429，提示 1 分钟）。
  - `test_settings.py`：新配置范围校验（含 backup 100/101 边界）。
  - `test_migrate.py` / `test_store_contract.py` / `test_web.py`：settings 行数与默认值、英文页面覆盖 auth 分组。
- 全量 `pytest`：**546 passed, 1 failed**（既有 `test_healthz.py::test_mcp_route_mounted`，与本次无关）；`ruff check .` 全过。
- 迁移在**真实数据副本**上验证：升级到 `0012_security_settings`，settings 共 13 行；
  `default_target_max_rows=1000` 原值保留，`backup_keep_count` 上限变为 100，审计数据未受影响。
- 截图（测试客户端渲染，Chrome 156）：
  - [认证与会话分组（Session / 登录保护 / MCP Token）](assets/ui/settings-auth-1440.webp)
  - [启动配置只读区（公网地址、远程监听）](assets/ui/settings-startup-1440.webp)

## 边界

- 登录失败保护为**进程内、按来源 IP**计数：重启清零，多实例各自计数；不做跨实例共享（如需要后续可落库）。
- Token 数量上限是「创建前检查」，极端并发创建可能短暂超出 1–2 个；不影响后续读取与删除。
- Token 有效期只作用于 MCP Bearer 认证；Web Session 仍由 `session_ttl_minutes` 控制，两者独立。
- `default_target_max_rows` 按决定保持 1000（用户明确不调回）。
- 历史 `settings_history` 里已有的 no-op 记录不回填/不清理。
- 无回填迁移；需要**重启服务**（启动时自动执行 0012 并自动备份 SQLite）。
