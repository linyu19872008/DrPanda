# 启动自动加载 .env 01 · 验证记录

背景：希望 `uv run dr-panda-mcp` 默认加载当前目录 `.env`，没有文件时按环境变量/默认值启动。
确认方案：新增 `python-dotenv` 依赖；只认当前目录 `./.env`；真实环境变量优先；文件权限过宽或格式非法时启动失败；不做禁用开关。

## 变更

| 层 | 改动 |
|---|---|
| 依赖 | `pyproject.toml` 新增 `python-dotenv>=1.0`；`uv.lock` 同步项目依赖与元数据 |
| 加载器 | 新增 `src/dr_panda_mcp/env.py`：`load_env_file()` 读当前目录 `.env`；不存在返回 `None`；校验普通文件、POSIX 权限（禁止 group/other 可读写）、逐行 `KEY=VALUE` / `export KEY=VALUE` 格式；用 `dotenv_values(interpolate=False)` 解析，`os.environ.setdefault` 保证真实环境变量优先 |
| 入口 | 新增 `src/dr_panda_mcp/cli.py`：先加载 `.env`，失败打印原因并退出 2；再调用现有服务/维护命令。`pyproject` 的 `dr-panda-mcp`、`dr-panda-mcp-admin` 入口与 `__main__.py` 都改为走它 |
| 不受影响 | 包内 `dr_panda_mcp.main()`、`dr_panda_mcp.admin.main()` 保持原样（不读 `.env`），测试/嵌入调用不受开发者本地 `.env` 影响 |
| 文档 | README 快速开始与环境变量段、`planning` 3.3、`.env.example` 头部改为“自动加载当前目录 ./.env + 优先级 + 失败规则” |

## 行为

- 当前目录有 `.env`：启动时加载；真实环境变量已存在时**不覆盖**（`systemd`/Docker/CI 注入优先）。
- 当前目录没有 `.env`：静默使用环境变量与代码默认值（与之前一致）。
- `.env` 权限不是 0600、不是普通文件、存在非 `KEY=VALUE`/`export KEY=VALUE` 行：启动失败（退出 2），stderr 给出文件路径和行号/权限原因。
- 只支持简单格式与注释，不支持多行值；不做变量插值。
- `dr-panda-mcp` 与 `dr-panda-mcp-admin` 都会先加载 `.env`。

## 验证

- 新增 `tests/test_env.py`（7 个用例）：缺失文件、真实环境变量优先、`export`/空值/注释、非法行、目录、权限过宽、CLI 成功加载与失败退出。
- 全量 `pytest`：**561 passed, 1 failed**（既有的 `test_healthz.py::test_mcp_route_mounted`，与本次无关）；`ruff check .` 全过。
- 手工验证：
  - 仓库现有 `.env`（0600）可被 `load_env_file()` 加载；
  - 临时目录放非法 `.env`、0644 `.env`，`python -m dr_panda_mcp` 均以退出码 2 失败并给出明确原因；
  - `dr-panda-mcp` / `dr-panda-mcp-admin` 的 console 脚本已指向 `dr_panda_mcp.cli`；
  - `uv run --offline python -c "import dotenv"` 可正常同步并运行（锁文件与依赖一致）。

## 边界

- 只加载当前工作目录 `.env`，不向上级/家目录搜索；服务场景需确认 `WorkingDirectory` 受控。
- `.env` 可能包含密钥：权限过宽会直接拒绝启动；文件值不会被打印。
- 不会覆盖真实环境变量；Docker/systemd 仍可用原生环境变量，无需挂载 `.env`。
- 测试/嵌入调用直接调用 `dr_panda_mcp.main()` 时不加载 `.env`（预期行为）。
- 没有禁用自动加载的开关（按确认的方案）。
