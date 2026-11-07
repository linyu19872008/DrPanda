# systemd 内一键客户端安装修复 1.2.1 · 验证记录

## 问题

1.2.0 已让新建/编辑目标表单支持一键安装客户端，但生产 systemd 服务使用：

```text
ProtectSystem=strict
ReadWritePaths=<dir>/data
```

同时服务 PATH 不包含安装脚本 root 用户的 `~/.local/bin`，也没有可写的 uv cache。因此服务进程执行：

```text
uv sync --extra mongo --inexact
```

会遇到：

- 找不到 `uv`；
- uv cache 不可写；
- `.venv` 在只读文件系统中，无法更新。

## 修复

`scripts/setup.sh` 的 unit 生成逻辑：

- 把当前 `uv` 复制到 `/usr/local/bin/uv`；
- 设置 `Environment=PATH=/usr/local/bin:/usr/bin:/bin`；
- 设置 `Environment=UV_CACHE_DIR=<dir>/data/.uv-cache`；
- `ReadWritePaths` 动态包含：
  - `<dir>/data`；
  - 已存在的 `.venv`；
  - 已存在的 `uv.lock`。

PyPI/tool 安装没有 `.venv` 时不会写入不存在的路径。

## 验证

- `bash -n scripts/setup.sh`：通过；
- 现有 Web/认证/安装客户端测试：全部通过；
- 需要在真实 Ubuntu 服务器重新执行 `setup.sh service` 后，用配置台安装一个缺失客户端做最终验收；
- macOS 当前环境无法执行 systemd 沙箱，因此 unit 的实际 systemd 行为仍以服务器验收为准。

## 部署提示

升级后必须刷新 unit：

```bash
cd /data/code/dr-panda-mcp
git pull --ff-only
uv sync --no-dev
sudo ./scripts/setup.sh service --dir /data/code/dr-panda-mcp
```

否则旧 unit 仍然是只读 `.venv`、没有 uv 路径。

## 1.2.2 补充

`setup.sh service` 现在在写 unit 前调用 `ensure_service_uv`，因此即使 `uv` 只安装在 `/root/.local/bin`，也会先复制到 `/usr/local/bin/uv`，再生成服务配置。

验证：

- `bash -n scripts/setup.sh`：通过；
- 全量测试：578 passed。
