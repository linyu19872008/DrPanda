# settings 表结构化改造

## 背景

原 `settings` 只有 `key/value/updated_at`，且迁移只 seed 了 2 行；后来的 5 个配置只存在于代码默认值中。外部 SQLite 查看器只能看到 2 行，无法判断分组、范围、默认值和是否可编辑。

## 迁移

`0002_settings_metadata`：

- 给 `settings` 增加：
  `value_type`、`group_key`、`group_title`、`label`、`description`、
  `default_value`、`min_value`、`max_value`、`unit`、`effect`、
  `editable`、`requires_restart`、`sort_order`、`updated_by`。
- 回填已有 2 行元数据，**不覆盖已有值**。
- 插入缺失的 5 行，共 7 个配置。
- 新增 `settings_history`：
  `key`、`old_value`、`new_value`、`actor`、`changed_at`。
- 索引：`key`、`changed_at`。

## 运行时

- `update_settings` 在同一事务里：
  - 更新 `settings.value / updated_at / updated_by`；
  - 插入一条结构化 `settings_history`；
  - 继续写一条 `audit` 作为跨资源索引。
- 设置页“最近变更”改为读 `settings_history`，不再解析 audit 字符串。
- 保留 `settings.py` 作为键白名单、范围校验和页面定义来源；数据库元数据用于自描述与审计，启动读取仍以代码校验为准。

## 验证

- 迁移后真实库：
  - 7 行配置全部存在；
  - `group_key/label/default/range/unit/effect` 完整；
  - `settings_history` 表存在。
- 新增测试：
  - 元数据 seed 完整；
  - 更新后历史保留 old/new；
  - 原有值迁移后不被默认值覆盖。
- 全量 `pytest`：**416 passed**；`ruff` 通过。

## 后续

- 元数据目前由迁移固定；未来新增配置必须同时补迁移和 `SettingSpec`，测试会校验两者一致。
- `settings_history` 暂未单独做保留期清理；后续可跟随 audit retention 或单独配置。
