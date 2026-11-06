# PyPI 1.0.0 发布 01 · 验证记录

背景：PyPI Pending Publisher 已配置（项目 `dr-panda-mcp`、仓库 `linyu19872008/DrPanda`、workflow `publish.yml`、environment `(Any)`），通过 Trusted Publishing 发布 1.0.0。

## 发布准备

- `.github/workflows/publish.yml`：GitHub Release `published` 触发；`id-token: write`；`uv build` + `pypa/gh-action-pypi-publish@release/v1`；
- `README.pypi.md`：由 `scripts/build_pypi_readme.py` 从 `README.md` 生成，把相对图片/链接改为 GitHub raw/blob 绝对地址，避免 PyPI 不解析相对路径；
- `pyproject.toml`：`readme = "README.pypi.md"`；
- CI docs job 增加 `python scripts/build_pypi_readme.py --check`，防止 README 与 PyPI 版不同步；
- GitHub Release：`v1.0.0`（target `main`）。

## 发布结果

- Publish workflow：**success**；
- PyPI：<https://pypi.org/project/dr-panda-mcp/>，版本 **1.0.0**；
- 包文件：`dr_panda_mcp-1.0.0-py3-none-any.whl`、`dr_panda_mcp-1.0.0.tar.gz`；
- 元数据：`License: MIT`、`Requires-Python: >=3.11`、Project URLs 指向 GitHub；
- PyPI 描述中包含绝对 raw 图片地址，无相对 `docs/assets/` 图片；
- README 已启用 PyPI 徽标，CI 徽标也已启用。

安装验证：

```bash
uv tool install dr-panda-mcp==1.0.0
```

## 待手动完成

Social preview 仍需网页上传 `docs/assets/social-preview.png`（GitHub 只支持 Web UI）：

```text
仓库 → Settings → General → Social preview → Upload an image
```

## 注意

- PyPI 1.0.0 已不可覆盖；后续修复必须发 1.0.1；
- README.pypi.md 是生成文件，修改 README.md 后必须运行 `python scripts/build_pypi_readme.py`；
- 本地 README 的 CI/PyPI 徽标是外链，离线预览可能裂图；License/Python 徽标是本地 PNG。
