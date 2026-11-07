# 变更记录

[English](CHANGELOG.md) · [简体中文](CHANGELOG.zh-CN.md)

记录本项目的显著变更。格式参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本遵循 [语义化版本](https://semver.org/)。

## [Unreleased]

## [1.1.2] - 2026-11-07

### 修复

- MySQL 迁移 0007 的 `batch.alter_column` 因 MySQL 要求提供现有列类型而失败；现在传入 `existing_type` 和 `existing_nullable`。
- 新增真实 MySQL/PostgreSQL 首次安装集成检查：完整 SetupApp 流程、页面、schema 校验和幂等迁移。
- CI 增加 MySQL 8.0 / PostgreSQL 16 service container 任务。

## [1.1.1] - 2026-11-07

### 修复

- MySQL 首次安装迁移在 `0007_environments` 中因 `key` 是 MySQL 保留字而失败；迁移改用 SQLAlchemy 表达式，由方言自动引用标识符。
- 新增 MySQL 方言下的环境查询/插入编译回归测试。

## [1.1.0] - 2026-11-06

### 新增

- 部署脚本 `scripts/setup.sh`：`check`、`install`、`service`、`start`、`status`、`upgrade`。
- source（`git + uv sync`）与 PyPI（`uv tool install`）两种安装方式。
- 专用 `drpanda` 用户的 systemd 服务、沙箱配置与健康检查启动。
- Python 自动选择（优先系统 >=3.11，fallback 到共享 `/opt/uv-python`）、生产 `--no-dev`、可选 PyPI/Python 镜像。
- 安装前后检查解释器可访问性、服务用户执行权限和 systemd unit 合法性。

### 变更

- 仓库从 `DrPanda` 重命名为 `dr-panda-mcp`，与包名/CLI 对齐。
- 文档默认英文在 `docs/`，中文在 `docs/zh-CN/`。

### 修复

- systemd unit 的路径指令不再使用引号。
- 服务启动失败不再被误报为安装成功。

## [1.0.0] - 2026-11-06

### 新增

- 面向 MySQL、MongoDB、Elasticsearch、Redis、GitLab、RabbitMQ、Kafka、CLS 的只读 MCP 服务。
- 配置台：目标登记、连接测试、加密密钥、环境与 MCP Token 管理。
- 首次安装向导、登录 Session、CSRF、登录失败锁定与 MCP Bearer Token。
- 审计日志：结果/失败详情、筛选与保留期清理。
- 系统配置：新建目标默认值、并发、审计维护、Session/Token 限制、备份保留。
- 自动加载 `./.env`，严格校验权限与格式，真实环境变量优先。
- 界面、MCP、CLI 与文档默认英文；中文文档在 `docs/zh-CN/`。
- GitHub 开源文档：双语 README、贡献/安全/行为准则、Issue/PR 模板与 CI。

### 安全

- 绝对只读闸门 + 危险/高开销规则 + 目标范围限制。
- 目标密钥加密保存，MCP Token 只存哈希；日志与审计不出现凭证。
- 可配置 Cookie Secure 策略与可选 `/mcp` Host 白名单。

### 说明

- Kafka、CLS、GitLab 工具已实现并有单测，但未用真实上游做端到端验收。
- 反向代理后的 HTTPS/TLS 部署仍需按环境自行验收。
