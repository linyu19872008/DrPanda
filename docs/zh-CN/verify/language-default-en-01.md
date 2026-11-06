# 默认语言英文 + 文档目录反转 01 · 验证记录

背景与决策：软件和文档默认英文；文档目录默认英文，中文放 `docs/zh-CN/`；Web i18n 采用 A（中文源 + 完整英文 catalog + 禁止回退）；历史中文验证记录保留不翻译；CLI/MCP English-only；只改新装默认环境标题。

## 文档目录

| 目标 | 结果 |
|---|---|
| 英文默认目录 | `docs/README.md`、`docs/architecture.md`、`docs/security.md`、`docs/ui-design.md`、`docs/verification.md` |
| 中文目录 | `docs/zh-CN/README.md`、`planning.md`、`milestones.md`、`ui-design.md`、`verify/`（历史记录保留） |
| 截图 | 英文 `docs/assets/screenshot-en.png`；中文 `docs/zh-CN/assets/screenshot-zh.png`；logo 共用 `docs/assets/logo.png` |
| README | 英文 README 只链英文文档；中文 README 只链 `docs/zh-CN/` 文档 |
| 链接检查 | `scripts/check_docs_links.py` 递归扫描 **68 个 Markdown 文件**，通过 |

## 软件

- Web：保持无 Cookie 默认 `en`；`en.json` 仍是完整英文 catalog；`t()` 在英文缺翻译时抛错，不再回退中文；
- 新装默认环境标题：迁移种子改为 `Default`；已有数据库不做回填（按决策只改新装）；
- MCP：server instructions、`investigate_error` prompt、28 个工具描述、参数说明、工具/guard/connector 错误全部英文；错误码与工具名不变；
- CLI/启动/配置/安装/密钥/日志：用户可见错误与提示英文；
- 代码内部注释与内部 docstring 仍保留中文（按决策不翻译）。

## 验证

- `ruff check .`：通过；
- 全量 `pytest`：**566 passed, 1 failed**（既有 `test_healthz.py::test_mcp_route_mounted`，中间件嵌套问题，与本次无关）；
- `python scripts/check_docs_links.py`：OK（68 个 Markdown 文件）；
- `tests/test_language_defaults.py`：英文 catalog 覆盖页面/表单/设置元数据 key；英文 catalog 值无中文；英文 README/docs 无中文；中文 README 只链中文文档；英文缺翻译不回退；
- `tests/test_mcp_inprocess.py`：MCP instructions/tool descriptions/参数 schema/prompt 无中文；
- `tests/test_startup.py`：CLI 启动失败提示为英文。

## 边界

- 历史中文验证文档只移动目录，不逐篇翻译；
- Web 的正常页面、表单校验与设置页使用完整 en catalog；少数底层异常原文（如存储层目标名校验）仍可能以中文源直接展示，尚未逐条接入 catalog，属于后续 i18n 债务；
- 已有安装的默认环境标题仍是之前写入的「默认」，不会自动迁移；
- README 图片仍为相对路径；PyPI 渲染需要在仓库公开后改绝对 raw URL。
