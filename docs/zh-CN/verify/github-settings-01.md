# GitHub 仓库设置 01 · 执行记录

背景：仓库已开源为 `https://github.com/linyu19872008/dr-panda-mcp`，默认分支 `main`；按计划补齐仓库设置、启用 CI 徽标。

## 已执行

### Topics

通过 GitHub API 设置 16 个 topics：

`ai-agents`、`database`、`elasticsearch`、`fastmcp`、`incident-response`、`kafka`、`mcp`、`model-context-protocol`、`mongodb`、`mysql`、`observability`、`python`、`rabbitmq`、`read-only`、`redis`、`troubleshooting`。

### Branch protection（main）

通过 GitHub API 设置：

- 必需状态检查：`test (Python 3.11)`、`test (Python 3.12)`、`build package`、`docs links`；
- 禁止 force push；
- 禁止删除分支；
- 不要求必须走 PR（个人维护阶段，避免直接推送被卡）；
- `enforce_admins: false`，管理员保留紧急绕过能力；
- 不要求 review approval、不要求 linear history。

### CI

最新 `main` 提交 `b37901a` 的 CI 已 **success**（test 3.11/3.12、build package、docs links 全部通过）。

### CI 徽标

README 顶部已启用 GitHub Actions CI 徽标；PyPI 徽标继续保留注释，等首次发布后启用。

## 待手动完成

### Social preview

已生成 1280×640 的 `docs/assets/social-preview.png`。GitHub 目前没有公开 REST/GraphQL 接口设置 social preview（Web UI only），需要在：

```text
仓库 → Settings → General → Social preview → Upload an image
```

上传该文件。

### PyPI

PyPI 1.0.0 已通过 Trusted Publishing 发布：<https://pypi.org/project/dr-panda-mcp/>；README 中 PyPI 徽标已启用。详见 `pypi-release-01.md`。

## 验证

- Topics API：HTTP 200，返回 16 个标签；
- Branch protection API：HTTP 200，required checks 已登记；
- `python scripts/check_docs_links.py`：OK（68 个 Markdown 文件）；
- `tests/test_language_defaults.py`：4 passed。
