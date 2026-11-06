# 为 DrPanda MCP 贡献代码

[English](CONTRIBUTING.md) · [简体中文](CONTRIBUTING.zh-CN.md)

感谢参与贡献。DrPanda MCP 是面向线上排障的只读 MCP 服务；削弱只读边界、暴露凭证或扩大目标授权范围的改动不会被接受。

## 开发环境

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/linyu19872008/DrPanda.git
cd dr-panda-mcp
uv sync --all-extras --dev
cp .env.example .env   # 可选；服务会自动加载 ./.env
```

提交 PR 前请跑完整检查：

```bash
uv run ruff check .
uv run pytest -q
uv run python scripts/smoke.py
uv run python scripts/check_docs_links.py
```

测试使用临时 SQLite 和临时密钥，不要指向生产系统。

## Pull request

- 改动保持聚焦；行为变化要带测试。
- 用户可见行为变更要更新文档（README、`docs/`）。
- 修改 `README.md` 时必须在同一个 PR 里同步改 `README.zh-CN.md`（`CONTRIBUTING`、`SECURITY`、`CODE_OF_CONDUCT`、`CHANGELOG` 的中英版本同理）。
- 说明改了什么、为什么改、怎么验证的；边界与未验证项要如实写。
- 不要在提交、issue 或测试里包含密钥、生产地址、Token 或客户数据。
- 提交即表示你的贡献按 MIT License 授权（见 [LICENSE](LICENSE)）。

## 上报安全问题

不要为安全漏洞开公开 issue，请按 [SECURITY.zh-CN.md](SECURITY.zh-CN.md) 上报。

## 语言

代码、注释、错误码和仓库治理文件以英文为准；界面与产品文档同时支持中文，issue/PR 可以用英文或中文。
