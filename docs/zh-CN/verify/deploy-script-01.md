# 部署脚本 01 · 验证记录

背景：新机器需要统一的环境检查/安装/启动入口。决策：同时支持 source（git + uv sync）与 PyPI（uv tool install）；生产使用 systemd + 专用用户 `drpanda`；允许脚本调用官方 uv 安装器；首次安装保持网页交互；暂不做 Docker。

## 新增

| 文件 | 作用 |
|---|---|
| `scripts/setup.sh` | 统一入口：`check` / `install` / `service` / `start` / `status` / `upgrade` |
| `docs/deployment.md` | 英文部署说明 |
| `docs/zh-CN/deployment.md` | 中文部署说明 |
| `.gitignore` | 忽略 `.drpanda-method` / `.drpanda-extras` / `.drpanda-version` 安装标记 |
| `.github/workflows/ci.yml` | docs job 增加 `bash -n scripts/setup.sh` |

## 行为

- `check`：只读；检查 OS、curl/git/uv、systemd、`.env` 权限、data/密钥文件、监听地址/端口、首次安装 loopback 限制；
- `install`：
  - source：仓库存在则 `uv sync`，否则 `git clone`；支持 `--extras`；
  - pypi：`UV_TOOL_DIR=<dir>/tool UV_TOOL_BIN_DIR=<dir>/bin uv tool install dr-panda-mcp[extras]==版本`；
  - 创建 `.env`（600）和 `data/`（700），不覆盖已有文件；
- `service`：Linux root；创建 `drpanda` 系统用户、修正归属、写 `/etc/systemd/system/dr-panda-mcp.service`，启停/健康检查；首次安装未完成且非 loopback 时只 enable 不 start；
- `start`：有 systemd 用服务，否则前台启动；启动前执行首次安装 loopback 检查；
- `upgrade`：按 source/PyPI 方式升级，可选重启服务。

## 验证

- `bash -n scripts/setup.sh`：通过；
- `check --dir <repo>`：只读，返回 0，输出警告（当前仓库不是通过脚本安装，无 marker）；
- PyPI 方式：临时目录安装 `dr-panda-mcp==1.0.0` 成功，生成 `bin/dr-panda-mcp`、`.env`、`data/`；随后 `check` 返回 0（仅 4 个首次安装前的密钥警告）；
- source 方式：在临时本地副本执行 `install --method source` 成功，生成 `.venv/bin/dr-panda-mcp`；`check` 返回 0；
- 首次安装 guard：把 `.env` 改为 `DR_PANDA_HOST="0.0.0.0"` 后执行 `start`，返回 1 并输出 loopback 提示；
- 首次安装前的前台启动：临时 PyPI 安装、端口 18111，执行 `start` 后 `/healthz` 返回 `200 {"ok":true,"installed":false}`；
- `ruff check .`：通过；
- 文档链接检查：72 个 Markdown 文件通过；
- CI 的 `bash -n` 步骤已加入。

## 未验证 / 边界

- systemd 服务安装与真实 Linux 启动未在当前 macOS 环境验证；需要 Ubuntu 22.04/24.04 云主机做一次端到端验收；
- 首次安装的浏览器交互未自动化（按决策保持网页交互）；
- 脚本不会自动创建管理员密码，也不会修改已存在的 `.env`/data/密钥；
- Docker 不在本脚本范围。
