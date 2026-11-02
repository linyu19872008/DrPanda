# 硬化 02：P0 安全与边界收口

本轮按 2026-11-02 的审计结论执行 P0；只读分析见对话记录，本文件记录代码与单测变更。

## 变更

| 项 | 现状 |
|---|---|
| MySQL PROCESSLIST | 新增 target 开关 `options.allow_processlist`，默认 **关闭**；`mysql_processlist` 与 `mysql_query(SHOW PROCESSLIST)` 都先检查该开关，关闭时返回 `SCOPE_DENIED` |
| Mongo 系统集合 | `mongo_find` / `mongo_aggregate` / `mongo_stats` 拒绝 `system.*`；`mongo_collections` 过滤系统集合；`$lookup.from` 引用 `system.*` 由 guard 拒绝 |
| ES size | `size < 0` 返回 `INVALID_ARGUMENT`，不再静默写成 0 |
| ES 聚合 | guard 对根级 `aggs` / `aggregations` 只放行有界 `terms`（size ≤ 100）；其他聚合类型返回 `DANGEROUS_OPERATION`。当前 `es_search` 没有独立 `aggs` 参数，普通查询仍以明细检索为主 |
| stats 字节上限 | 统一包络的 `stats` 超过 target `max_bytes` 时替换为 `{"truncated":true,"reason":"bytes"}` 并加 note |
| MySQL LIMIT | 用户 SQL 已有更小 `LIMIT` 时保留，不再被强制放大到目标上限 |
| CLS 上下文 | `cls_context` 增加 `btime`、`pkg_log_id`，请求传 `BTime/PkgLogId/PrevLogs/NextLogs`；读取 `LogContextInfos`；`cls_search` 返回 `package_id/package_log_id/btime` 供上下文使用 |
| CLS 时间窗 | `max_window_minutes` 现在由 target 传入 guard 生效，不再固定 24 小时 |

## 验证

- 新增/更新单测覆盖：
  - PROCESSLIST 默认拒绝、显式开启后允许
  - Mongo `system.*` 拒绝、集合列表过滤、`$lookup` 系统集合拒绝
  - ES 负数 size、聚合类型/terms 上限、根级 aggs guard
  - stats 字节上限
  - CLS target 最大窗口、context 请求字段、返回字段
- `pytest` 全量通过，`ruff` 全过；本轮未重跑 Docker 联调，真实行为以单测为准。
- `register_targets.sh` 的 MySQL 基础 target 显式开启 `allow_processlist=on`，保持原有联调冒烟可用。

## 仍未完成

- 上游 HTTP 响应体/文件流的真正 IO 级上限（当前 stats/行/字节是解析后截断）
- CLS `default_window_minutes` 的实际省略默认窗口（当前仍要求显式 from/to）
- ES 独立 `aggs` 参数/更细的有界聚合能力
- GitLab / CLS / Kafka 真实上游
