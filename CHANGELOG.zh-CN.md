# 变更记录

[English](CHANGELOG.md) · [简体中文](CHANGELOG.zh-CN.md)

记录本项目的显著变更。格式参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本遵循 [语义化版本](https://semver.org/)。

## [Unreleased]

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
