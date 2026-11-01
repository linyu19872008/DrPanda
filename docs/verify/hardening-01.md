# 复核硬化 01 · 验证记录

依据 2026-11-02 的只读复核结论执行；本记录不含排期信息，也不改变既有里程碑的完成状态。

## 修复项

| 项 | 修复 | 验证 |
|---|---|---|
| MySQL 可执行版本注释 `/*!...*/` | 解析前直接拒绝，错误码 `DANGEROUS_OPERATION` | `tests/test_guards.py` 新增两条拒绝用例 |
| 工具级并发 | `run_tool` 在解析目标后获取 `catalog.slot`，与测试连接共用 `target_max_concurrency` | 11 并发工具调用断言 `max_active <= 10` |
| 工具级超时 | `run_tool` 用 `asyncio.timeout` 包住"排队 + 执行"，超时映射 `UPSTREAM_TIMEOUT` | 慢 fake 连接器断言超时错误码 |
| 截断哨兵 | MySQL / Mongo / ES / GitLab / CLS / Kafka peek 使用 `cap+1` 探测；显式截断仍受字节上限约束 | 既有截断用例 + 各工具测试更新 |
| 必填密钥 | 编辑时勾选清除必填密钥返回 400，不允许静默保存空密钥 | `tests/test_web.py` 新增用例 |
| MySQL SSL | `_connect` 在 `ssl=true` 时传入 `SSLContext` | `tests/test_connectors_probe.py` 断言 |
| `/theme` 重定向 | 拒绝反斜杠及其 URL 编码变体、控制字符 | `tests/test_web.py` 新增用例 |
| Redis `SLOWLOG` 范围 | 配置 `key_prefix` 时只返回含该前缀 key 的慢日志条目 | `tests/test_tools_data.py` 过滤用例 |
| ES 多 host | 请求失败/5xx 时按配置顺序尝试下一个 host | 连接器测试仍通过；未做真实集群验证 |
| Mongo URI | user / password / authSource 做 URL 编码 | `tests/test_connectors_data.py` 特殊字符用例 |
| SQLite 备份 | 改用 sqlite3 backup API，包含 WAL 中已提交事务 | `tests/test_migrate.py` WAL 备份用例 |
| 连接器缓存 | `Catalog.client` 加锁；文档改为"连接器缓存"而非连接池 | `tests/test_catalog.py` 全过 |
| 非 loopback 监听 | M7 前只允许 `127.0.0.1` / `::1` / `localhost` | `tests/test_config.py` 断言 host 判定 |
| UTC 时间/摘要 | CLS `time_range` 与 `systems_status` 时间改 `Z`；包络 summary 截 200 | 既有测试更新 |

## 检查结果

| 检查 | 结果 |
|---|---|
| 全量测试 | **371 passed** |
| 静态检查 | `ruff check .` 全过 |
| 冒烟 | healthz + 28 工具 + `systems_status` 通过 |
| 非 loopback 拦截 | `DR_PANDA_HOST=0.0.0.0` 启动返回 2，并打印可操作错误 |

## 仍待处理

- 真实 MySQL / Mongo / ES / Redis / RabbitMQ / Kafka / CLS / GitLab 的连通性与返回结构仍需 extras + 只读凭证手测。
- schema/list 类接口没有上游 limit，无法用 `cap+1` 判断"恰好等于上限"；已在 planning 8.3 写明。
- `cls_context` 的 before/after 目前只做参数校验，CLS API 上下文条数限制仍需真实实例确认。
- 非 loopback 拦截是 M7 前的临时保护；M7 完成后应改为认证 + 受控监听。
