# GitHub 开源文档 01 · 验证记录

背景：按 MIT、英文 README 默认、中英双语辅助文档、GitHub 规范、支持 PyPI、本期启用 CI 与徽标的决定，完成开源文档改造。

## 变更

| 层 | 改动 |
|---|---|
| License | 新增 `LICENSE`（MIT，2026）；`pyproject.toml` 增加 `license = "MIT"`、`license-files` |
| README | 原中文 README 改为 `README.zh-CN.md`；新增英文 `README.md`（同章节结构）；两篇顶部加语言切换、徽标与居中 logo |
| 徽标 | CI（GitHub Actions）、PyPI、MIT、Python 3.11+；CI 徽标指向 `.github/workflows/ci.yml` |
| 图片 | 两篇 README 使用 GitHub raw 绝对地址，保证 PyPI 能渲染；原 `docs/assets/logo.png` 继续作为来源 |
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
- GitHub Actions 尚未在 GitHub 实际运行（仓库当前只有 Gitee remote）；工作流内容按本地等价命令编写。

## 假设与待调整

- GitHub 仓库路径按 `github.com/jacklin_zjut/dr-panda-mcp`（从 Gitee owner 推断）编写，默认分支按 `master`；如果实际 GitHub owner/仓库名/分支不同，需要同步替换：
  - README/README.zh-CN 顶部徽标与 raw 图片地址；
  - `.github/ISSUE_TEMPLATE/config.yml` 的 SECURITY/文档链接；
  - `pyproject.toml` 的 `[project.urls]`；
  - `CONTRIBUTING*` 的 clone 地址。
- PyPI 尚未实际发布：已通过 `uv build` 验证元数据与包结构；发布前需要配置 PyPI 项目与（可选）可信发布。
- GitHub Issue/PR 模板保持英文（GitHub 无按语言切换机制），正文可用中英文填写；治理文档提供中英双版本。
- README 中文设计文档链接仍指向中文 `docs/`；英文 README 已标注 "currently written in Chinese"。
