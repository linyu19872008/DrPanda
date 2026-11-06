# 版本定为 1.0.0 · 验证记录

背景：将当前版本从 0.1.0 定为 1.0.0，作为面向 GitHub/PyPI 的首个正式发布版本。

## 变更

| 文件 | 改动 |
|---|---|
| `pyproject.toml` | `version = "1.0.0"` |
| `uv.lock` | 项目自身版本同步为 `1.0.0` |
| `CHANGELOG.md` / `CHANGELOG.zh-CN.md` | 首个版本条目改为 `[1.0.0] - 2026-11-06` |
| `README.md` / `README.zh-CN.md` | `/healthz` 示例版本改为 `1.0.0` |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | 版本示例改为 `1.0.0` |
| `docs/planning.md` | 发布 tag 计划改为 `v1.0.0` |

## 验证

- `uv run --offline python -c "importlib.metadata.version('dr-panda-mcp')"` → `1.0.0`；
- `uv build --offline` 成功生成 `dr_panda_mcp-1.0.0.tar.gz` / `.whl`，wheel `METADATA` 中
  `Version: 1.0.0`、`License-Expression: MIT`、`License-File: LICENSE`；
- `python scripts/check_docs_links.py`：OK（10 个 markdown 文件）；
- `ruff check .`：通过；
- 全量 `pytest`：**561 passed, 1 failed**（既有的 `test_healthz.py::test_mcp_route_mounted`，与本次无关）。

## 后续

- 发布时需打 `v1.0.0` tag，并在 PyPI 发布同名版本；
- GitHub 仓库路径/默认分支如与 README 中的假设不一致，仍需同步替换徽标与 raw 图片地址。
