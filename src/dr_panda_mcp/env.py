"""启动时自动加载当前目录 ``.env``（环境变量优先，文件只补缺）。

规则：
- 只认当前工作目录的 ``.env``；文件不存在时静默使用环境变量与默认值；
- 真实环境变量始终优先（``os.environ.setdefault``），便于 systemd / Docker / CI 覆盖；
- 文件权限过宽、不是普通文件、行格式非法时抛 ``EnvFileError``，由入口按启动失败处理；
- 只支持简单的 ``KEY=VALUE`` / ``export KEY=VALUE`` / 注释，不支持多行值。

值不会被打印；调用方只按需记录路径或错误原因。
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from dotenv import dotenv_values

ENV_FILE_NAME = ".env"
_LINE = re.compile(r"^(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=")


class EnvFileError(Exception):
    """``.env`` 无法读取、权限异常或格式非法。"""


def load_env_file(path: Path | None = None) -> Path | None:
    """加载 ``.env`` 并返回路径；文件不存在返回 ``None``。"""
    target = path if path is not None else Path.cwd() / ENV_FILE_NAME
    try:
        info = target.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise EnvFileError(f"无法读取 {target}：{exc}") from exc

    if not stat.S_ISREG(info.st_mode):
        raise EnvFileError(f"{target} 不是普通文件")
    if os.name == "posix" and info.st_mode & 0o077:
        raise EnvFileError(
            f"{target} 权限过宽（{oct(info.st_mode & 0o777)}），"
            "可能包含密钥，请 chmod 600 后重启"
        )

    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EnvFileError(f"无法读取 {target}：{exc}") from exc

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not _LINE.match(stripped):
            raise EnvFileError(
                f"{target} 第 {lineno} 行不是合法的 KEY=VALUE 或 export KEY=VALUE"
            )

    try:
        values = dotenv_values(target, interpolate=False, encoding="utf-8")
    except Exception as exc:
        raise EnvFileError(f"解析 {target} 失败：{exc}") from exc

    for key, value in values.items():
        if not key or value is None:
            continue
        os.environ.setdefault(key, value)
    return target
