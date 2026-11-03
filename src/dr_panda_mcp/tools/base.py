"""工具公共层：错误码映射、目标解析、审计与统一包络（planning 8.1–8.3）。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastmcp.exceptions import ToolError
from pydantic import Field

from dr_panda_mcp import auth, errors
from dr_panda_mcp.connectors import base as connectors_base
from dr_panda_mcp.masking import redact
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.protocol import AuditEntry, Target

logger = logging.getLogger(__name__)

TOOL_ANNOTATIONS = {"readOnlyHint": True}

EnvironmentParam = Annotated[
    str,
    Field(
        description=(
            "环境调用标识 key，不是展示名。"
            "用户说乐畅生产这类名字时，先用 systems_status 对照 title 得到 key。"
            "登记了多个环境时必填；只有一个环境时可以省略。"
            "同一种类型有多台时仍必须另传 target，不会自动挑选。"
        )
    ),
]

_ERROR_CODES: tuple[tuple[type[errors.DrPandaError], str], ...] = (
    (errors.TargetNotFound, errors.TARGET_NOT_FOUND),
    (errors.TargetDisabled, errors.TARGET_DISABLED),
    (errors.TargetTypeMismatch, errors.TARGET_TYPE_MISMATCH),
    (errors.EnvironmentRequired, errors.ENVIRONMENT_REQUIRED),
    (errors.EnvironmentNotFound, errors.ENVIRONMENT_NOT_FOUND),
    (errors.EnvironmentDisabled, errors.ENVIRONMENT_DISABLED),
    (errors.SecretUnavailable, errors.SECRET_UNAVAILABLE),
    (errors.ScopeDenied, errors.SCOPE_DENIED),
    (errors.InvalidArgument, errors.INVALID_ARGUMENT),
    (errors.UpstreamTimeout, errors.UPSTREAM_TIMEOUT),
    (errors.UpstreamNotFound, errors.UPSTREAM_NOT_FOUND),
    (errors.UpstreamUnavailable, errors.UPSTREAM_UNAVAILABLE),
    (errors.StorageUnavailable, errors.STORAGE_UNAVAILABLE),
)


def code_for(exc: errors.DrPandaError) -> str:
    if isinstance(exc, errors.GuardRejected):
        return exc.code or errors.GUARD_REJECTED
    for exception_type, code in _ERROR_CODES:
        if isinstance(exc, exception_type):
            return code
    return errors.INTERNAL


def mask_params(params: dict[str, Any], target: Target | None) -> str:
    raw = json.dumps(params, ensure_ascii=False, default=str)
    secrets = list(target.secret.values()) if target else []
    return redact(raw, secrets)[:200]


def _client_prefix() -> str:
    client = auth.current_client()
    if client is None:
        return ""
    return f"client={client.name or '-'} prefix={client.prefix or '-'} "


async def write_tool_audit(
    runtime: Runtime,
    *,
    tool: str,
    name: str,
    environment_key: str | None,
    params: dict[str, Any],
    target: Target | None,
    returned: int,
    started: float,
    error_code: str | None,
) -> None:
    """工具调用结束后追加一条审计。写失败不影响工具结果。"""
    env_label = environment_key or "-"
    summary = (
        f"{_client_prefix()}{tool} env={env_label} target={name or '-'} "
        f"params={mask_params(params, target)} returned={returned} "
        f"elapsed_ms={int((time.monotonic() - started) * 1000)} "
        f"error={error_code or '-'}"
    )
    try:
        await runtime.store.append_audit(
            AuditEntry(
                actor=auth.current_actor(),
                action="tool.call",
                target_name=name or None,
                summary=summary[:1024],
                environment_key=environment_key or None,
            )
        )
    except Exception:
        logger.warning("工具审计写入失败：%s", tool, exc_info=True)


async def run_tool(
    runtime: Runtime,
    *,
    tool: str,
    name: str,
    target_type: str,
    params: dict[str, Any],
    handler: Callable[[Target], Awaitable[dict[str, Any]]],
    environment: str = "",
) -> dict[str, Any]:
    """解析目标 → 执行 → 统一错误码与审计（审计失败不影响结果）。"""
    started = time.monotonic()
    environment = (environment or str(params.get("environment") or "")).strip()
    target: Target | None = None
    returned = 0
    error_code: str | None = None
    timeout = connectors_base.DEFAULT_TIMEOUT_SECONDS
    try:
        target = await runtime.catalog.resolve(
            name, environment=environment, expected_type=target_type
        )
        timeout = connectors_base.timeout_seconds(target)
        # 整个调用（含排队）共用同一个 deadline；排队时间计入超时（planning 8.3/9.3）。
        async with asyncio.timeout(timeout):
            async with runtime.catalog.slot(target):
                envelope = await handler(target)
        returned = int(envelope.get("returned", 0))
        return envelope
    except ToolError:
        raise
    except TimeoutError as exc:
        error_code = errors.UPSTREAM_TIMEOUT
        raise ToolError(
            f"{errors.UPSTREAM_TIMEOUT}: 工具调用超过 {timeout:.0f} 秒（含排队），目标可能繁忙"
        ) from exc
    except errors.DrPandaError as exc:
        error_code = code_for(exc)
        message = redact(str(exc), target.secret.values() if target else [])
        raise ToolError(f"{error_code}: {message}") from exc
    except Exception as exc:
        error_code = errors.INTERNAL
        logger.exception("工具执行失败：%s", tool)
        raise ToolError(f"{errors.INTERNAL}: 工具执行失败（{type(exc).__name__}）") from exc
    finally:
        environment_key = (
            target.environment_key
            if target is not None and target.environment_key
            else (environment or None)
        )
        await write_tool_audit(
            runtime,
            tool=tool,
            name=name,
            environment_key=environment_key,
            params=params,
            target=target,
            returned=returned,
            started=started,
            error_code=error_code,
        )


def finish(
    target: Target,
    *,
    summary: str,
    started: float,
    rows: list[dict[str, Any]],
    stats: dict[str, Any] | None = None,
    time_range: dict[str, str] | None = None,
    truncation: connectors_base.Truncation | None = None,
) -> dict[str, Any]:
    """按目标上限截断并生成 11 键包络。

    调用方已显式截断（例如文件内容）时只标记、不再二次裁行，避免把行整条丢掉。
    """
    kept, auto_truncation = connectors_base.apply_row_limits(
        rows, connectors_base.max_rows(target), connectors_base.max_bytes(target)
    )
    effective = truncation or auto_truncation
    notes = ["结果已截断，请缩小查询范围、时间窗或返回条数。"] if effective else []
    if target.environment_key:
        label = target.environment_title or target.environment_key
        notes.insert(0, f"环境 {target.environment_key}（{label}）。")
    stats, stats_truncated = _cap_stats(stats, connectors_base.max_bytes(target))
    if stats_truncated:
        notes.append("统计信息已因目标字节上限被截断。")
    return connectors_base.build_envelope(
        target,
        summary=summary[:200],
        elapsed_ms=int((time.monotonic() - started) * 1000),
        rows=kept,
        stats=stats,
        time_range=time_range,
        truncation=effective,
        notes=notes,
    )


def _cap_stats(
    stats: dict[str, Any] | None, byte_limit: int
) -> tuple[dict[str, Any] | None, bool]:
    if stats is None:
        return None, False
    raw = json.dumps(stats, ensure_ascii=False, default=str).encode("utf-8")
    if len(raw) <= byte_limit:
        return stats, False
    return {"truncated": True, "reason": "bytes", "limit": byte_limit}, True


def trim_rows(
    rows: list[dict[str, Any]], cap: int
) -> tuple[list[dict[str, Any]], connectors_base.Truncation | None]:
    """用 cap+1 哨兵判断是否还有更多数据；返回前 cap 行与截断信息。"""
    if len(rows) > cap:
        return rows[:cap], connectors_base.Truncation("rows", cap)
    return rows, None


def ensure_topic(target: Target, topic: str) -> str:
    """校验日志主题在授权范围内。"""
    allowed = [str(item) for item in target.options.get("allowed_topics", [])]
    if not allowed:
        raise errors.ScopeDenied(f"目标 {target.name} 没有授权任何日志主题")
    value = topic.strip()
    if not value and len(allowed) == 1:
        return allowed[0]
    if not value:
        raise errors.InvalidArgument("必须指定 topic（该目标授权了多个主题）")
    if value not in allowed:
        raise errors.ScopeDenied(f"主题 {value} 不在目标 {target.name} 的授权范围内")
    return value


def ensure_project(target: Target, project: str) -> str:
    allowed = [str(item) for item in target.options.get("allowed_projects", [])]
    value = project.strip()
    if not allowed:
        raise errors.ScopeDenied(f"目标 {target.name} 没有授权任何项目")
    if value not in allowed:
        raise errors.ScopeDenied(f"项目 {value} 不在目标 {target.name} 的授权范围内")
    return value


def allowed_projects(target: Target) -> list[str]:
    values = [str(item) for item in target.options.get("allowed_projects", [])]
    if not values:
        raise errors.ScopeDenied(f"目标 {target.name} 没有授权任何项目")
    return values


def clamp_limit(value: int | None, target: Target, default: int) -> int:
    limit = default if value is None else int(value)
    if limit < 1:
        raise errors.InvalidArgument("limit 必须大于 0")
    return min(limit, connectors_base.max_rows(target))
