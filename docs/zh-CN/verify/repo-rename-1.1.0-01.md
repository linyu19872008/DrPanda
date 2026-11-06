# 仓库重命名与 1.1.0 版本 01 · 验证记录

背景：将 GitHub 仓库从 `DrPanda` 重命名为 `dr-panda-mcp`，与 PyPI 包名、CLI 保持一致；同时将版本从 1.0.0 升级到 1.1.0。

## 仓库重命名

- 通过 GitHub API 将 `linyu19872008/DrPanda` 重命名为 `linyu19872008/dr-panda-mcp`；
- 默认分支仍为 `main`；
- 本地 `origin` 已更新为新仓库地址；
- GitHub 会保留旧仓库 URL 的跳转，但仓库内所有链接已改为新地址：
  - README / README.zh-CN / README.pypi
  - CONTRIBUTING / SECURITY
  - `.github/ISSUE_TEMPLATE/config.yml`
  - `pyproject.toml` 的 `[project.urls]`
  - `scripts/setup.sh` 的 `REPO_URL`
  - `scripts/build_pypi_readme.py` 的 GitHub 地址
  - docs 中的当前仓库引用
  - Social preview 中的 URL

## 版本 1.1.0

- `pyproject.toml` / `uv.lock`：`version = "1.1.0"`；
- `CHANGELOG.md` / `CHANGELOG.zh-CN.md`：新增 1.1.0 条目；
- README 健康检查示例、部署示例、Issue 模板示例更新为 1.1.0；
- `scripts/setup.sh` 默认 PyPI 版本更新为 1.1.0；
- PyPI README（`README.pypi.md`）重新生成，包含新仓库 raw 地址和 1.1.0 示例。

## 验证

- `uv run --offline` 读取版本：**1.1.0**；
- `uv build --offline`：成功生成 `dr_panda_mcp-1.1.0` sdist + wheel；
- wheel `METADATA`：
  - `Version: 1.1.0`
  - Homepage/Repository/Issues/Documentation/Changelog 均指向 `linyu19872008/dr-panda-mcp`
  - PyPI 描述中的图片使用新 raw URL；
- `python scripts/build_pypi_readme.py --check`：通过；
- 文档链接检查：通过；
- `ruff check .`：通过。

## 发布结果

- CI 通过；
- `v1.1.0` GitHub Release 已发布；
- 首次 Publish 因 PyPI Trusted Publisher 仍记录旧仓库名 `DrPanda` 失败；
- 更新 PyPI Trusted Publisher 为 `dr-panda-mcp` 后重跑成功；
- PyPI 已发布 **1.1.0**：<https://pypi.org/project/dr-panda-mcp/1.1.0/>；
- README PyPI 徽标 cache 参数更新为 `?cache=1.1.0`；
- PyPI 1.0.0 的已发布元数据仍指向旧仓库 URL，无法修改；1.1.0 起使用新 URL。

## 边界

- GitHub 重命名后旧 URL 重定向通常有效，但 raw 图片/徽标/外部引用不应依赖跳转；
- GitHub Actions 的 badge 路径已随仓库名更新；
- Branch protection 与 topics 随仓库保留。

## PyPI Trusted Publisher 的重要变更

仓库改名后，PyPI 上已有的 trusted publisher 仍然记录旧仓库名：

```text
linyu19872008/DrPanda
```

1.1.0 发布前必须在 PyPI 项目设置中更新为：

```text
Publisher: GitHub
Owner: linyu19872008
Repository: dr-panda-mcp
Workflow: publish.yml
Environment: (Any)
```

否则 GitHub OIDC 的 repository claim 与 PyPI 记录不一致，publish workflow 会失败。

已准备 `v1.1.0` GitHub Release（draft），更新 PyPI trusted publisher 后再发布，触发 Trusted Publishing。

## 发布后待办

- 确认 PyPI 1.1.0；
- README PyPI 徽标 cache 参数改为 `?cache=1.1.0`；
- 检查新仓库 raw 图片地址；
- 旧 1.0.0 元数据仍指向旧仓库 URL，属于历史发布记录，无法修改。
