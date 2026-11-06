"""控制台入口：先加载当前目录 ``.env``，再运行服务或维护命令。

保持 ``dr_panda_mcp.main`` / ``dr_panda_mcp.admin.main`` 本身不读 ``.env``，
避免单元测试或嵌入调用被开发者本地文件影响。
"""

from __future__ import annotations

import sys

from dr_panda_mcp import main as serve_main
from dr_panda_mcp.admin import main as admin_command
from dr_panda_mcp.env import EnvFileError, load_env_file


def _load_env() -> bool:
    try:
        load_env_file()
    except EnvFileError as exc:
        print(f"dr-panda-mcp: 启动失败：{exc}", file=sys.stderr)
        return False
    return True


def main() -> int:
    if not _load_env():
        return 2
    return serve_main()


def admin_main() -> int:
    if not _load_env():
        return 2
    return admin_command()
