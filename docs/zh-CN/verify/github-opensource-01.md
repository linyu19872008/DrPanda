# GitHub 开源文档 01 · 验证记录

背景：按 MIT、英文 README 默认、中英双语辅助文档、GitHub 规范、支持 PyPI、本期启用 CI 与徽标的决定，完成开源文档改造。

## 变更

| 层 | 改动 |
|---|---|
| License | 新增 `LICENSE`（MIT，2026）；`pyproject.toml` 增加 `license = "MIT"`、`license-files` |
| README | 原中文 README 改为 `README.zh-CN.md`；新增英文 `README.md`（同章节结构）；两篇顶部加语言切换、徽标与居中 logo |
| 徽标 | CI（GitHub Actions）、PyPI、MIT、Python 3.11+；CI 徽标指向 `.github/workflows/ci.yml` |
| 图片 | 两篇 README 使用**相对路径**（`docs/assets/...`），GitHub/Gitee 页面可直接渲染；原 `docs/assets/logo.png` 继续作为来源。PyPI 渲染需要公开仓库的绝对 raw URL，见“假设与待调整” |
| 开源治理 | `CONTRIBUTING` / `SECURITY` / `CODE_OF_CONDUCT` / `CHANGELOG` 均提供英文 + `*.zh-CN.md` 中文版 |
| GitHub 模板 | `.github/ISSUE_TEMPLATE/`（bug/feature/config）、`.github/PULL_REQUEST_TEMPLATE.md` |
| CI | `.github/workflows/ci.yml`：Python 3.11/3.12 跑 ruff + pytest；独立 job 做 `uv build`；文档 job 跑链接检查 |
| 链接检查 | 新增 `scripts/check_docs_links.py`（只检查本地相对链接/图片，跳过 http(s)，无网络依赖） |
| 包元数据 | `pyproject.toml` 增加 license、keywords、classifiers、`[project.urls]`（Homepage/Repository/Issues/Documentation/Changelog） |
| README 状态 | 删除过期的硬编码测试数量（465/442），改为以 CI 徽标与实际运行结果为准；补充 PyPI 安装方式 |

## 验证

- `python scripts/check_docs_links.py`：**OK: checked 10 markdown files**。
- `uv build --offline`：成功生成 sdist + wheel；wheel `METADATA` 含
  `License-Expression: MIT`、`License-File: LICENSE`、`Project-URL` 与 classifiers。
- `uv run ruff check .`：通过。
- 全量 `pytest`：**561 passed, 1 failed**（既有的 `test_healthz.py::test_mcp_route_mounted`，与本次无关）。
- GitHub Actions 已在 GitHub 实际运行；早期 test job 因 `test_healthz.py::test_mcp_route_mounted` 只解开一层中间件导致失败，已修复并推送；`main` 提交 `b37901a` 的 CI 已全部通过。

## 仓库信息与待办

- GitHub 仓库已确认：`github.com/linyu19872008/DrPanda`，默认分支 `main`；README、模板、SECURITY、CONTRIBUTING、pyproject 已按此更新：
  - README/README.zh-CN 顶部徽标链接；
  - `.github/ISSUE_TEMPLATE/config.yml` 的 SECURITY/文档链接；
  - `pyproject.toml` 的 `[project.urls]`；
  - `CONTRIBUTING*` 的 clone 地址。
- PyPI 尚未实际发布：已通过 `uv build` 验证元数据与包结构；发布前需要配置 PyPI 项目与（可选）可信发布。
- GitHub Issue/PR 模板保持英文（GitHub 无按语言切换机制），正文可用中英文填写；治理文档提供中英双版本。
- 文档默认英文在 `docs/`，中文在 `docs/zh-CN/`；英文 README 只链英文文档，中文 README 只链中文文档。


## 关于 README 裂图的修复

- 之前 README 使用 `raw.githubusercontent.com/jacklin_zjut/...` 的绝对图片地址，GitHub 页面实际无法加载（owner 不存在/仓库未公开），因此显示裂图；
- 现已改为相对路径 `docs/assets/logo.png` 与 `docs/zh-CN/verify/assets/ui/light-index.png`，GitHub 仓库页可直接渲染，且不依赖仓库是否公开；
- **PyPI 页面不解析相对图片**：等 GitHub 仓库公开、确认 owner/分支后，发布到 PyPI 前需把图片改为绝对 raw URL（或在发布脚本中替换）；
- CI / PyPI 徽标在仓库公开并且首次发布前会显示 404 / "package or version not found"，因此已在 README 中暂时移除，并保留 HTML 注释；仓库公开、Actions 跑过、PyPI 发布后取消注释即可恢复。
