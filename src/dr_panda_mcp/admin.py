"""本地管理员维护命令。

用法：
    uv run dr-panda-mcp-admin reset-password

只允许在本机执行，提示输入两次新密码；成功后递增 auth_version，
使所有现有网页 Session 失效。MCP Token 不受影响。
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from dataclasses import replace

from dr_panda_mcp import auth
from dr_panda_mcp.config import load_config
from dr_panda_mcp.install import load_install_state
from dr_panda_mcp.runtime import Runtime, create_runtime
from dr_panda_mcp.store.protocol import AuditEntry


async def reset_admin_password(runtime: Runtime, password: str) -> None:
    problem = auth.password_problem(password)
    if problem:
        raise ValueError(
            {
                "密码至少需要 8 位": "password must be at least 8 characters",
                "密码不能超过 256 位": "password must be at most 256 characters",
                "登录名只能使用小写字母、数字和连字符": "use lowercase letters, digits, and hyphens",
            }.get(problem, problem)
        )
    user = await auth.get_user_by_username(runtime.session_factory, "admin")
    if user is None:
        raise ValueError("no admin user in the config store")
    await auth.set_password(
        runtime.session_factory,
        user.id,
        await asyncio.to_thread(auth.hash_password, password),
    )
    await runtime.store.append_audit(
        AuditEntry(
            actor="local-cli",
            action="user.password_change",
            summary="admin password reset via local CLI; sessions invalidated",
        )
    )


def _prompt_password() -> str:
    password = getpass.getpass("New admin password: ")
    confirm = getpass.getpass("Confirm new admin password: ")
    if password != confirm:
        raise ValueError("passwords do not match")
    return password


async def _run_reset() -> int:
    config = load_config()
    state = load_install_state(config.install_file, config.install_key_file)
    if state is None:
        print("installation state not found; complete setup first", file=sys.stderr)
        return 2
    cfg = replace(config, database_url=state.database_url)
    runtime = await create_runtime(cfg)
    try:
        password = _prompt_password()
        await reset_admin_password(runtime, password)
    finally:
        await runtime.close()
    print("administrator password reset; sign in with the new password.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="dr-panda-mcp-admin")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reset-password", help="reset the local admin password")
    args = parser.parse_args()
    if args.command == "reset-password":
        try:
            return asyncio.run(_run_reset())
        except (ValueError, OSError) as exc:
            print(f"reset failed: {exc}", file=sys.stderr)
            return 2
    return 2
