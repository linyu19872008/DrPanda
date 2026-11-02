"""网页视图模型：把 Target 转成不含密钥的展示数据（planning 4.3 / 5.2）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dr_panda_mcp.store.protocol import Target
from dr_panda_mcp.web.forms import TYPE_SPECS

EMPTY = "—"


@dataclass(frozen=True)
class TargetView:
    id: int
    type: str
    type_label: str
    name: str
    enabled: bool
    endpoint: str
    scope: str
    scope_source: str
    scope_params: dict[str, Any]
    secret_fields: tuple[str, ...]
    secret_ok: bool
    updated_at_display: str | None
    last_test_at_display: str | None
    last_test_ok: bool | None
    last_test_error: str | None


@dataclass(frozen=True)
class Stats:
    total: int = 0
    enabled: int = 0
    failed: int = 0
    key_issues: int = 0


def _display_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _first(value: Any) -> str | None:
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else None
    if isinstance(value, str):
        return value.splitlines()[0].strip() or None
    return None


def _endpoint(target: Target) -> str:
    options = target.options
    kind = target.type
    if kind == "mysql":
        host = options.get("host") or EMPTY
        port = options.get("port") or 3306
        db = options.get("default_db") or EMPTY
        return f"{host}:{port} / {db}"
    if kind == "mongo":
        host = options.get("host")
        if host:
            return f"{host}:{options.get('port') or 27017}"
        return "URI（已配置）"
    if kind == "elasticsearch":
        host = _first(options.get("hosts"))
        return host or EMPTY
    if kind == "redis":
        host = options.get("host") or EMPTY
        port = options.get("port") or 6379
        db = options.get("db") or 0
        return f"{host}:{port} / db{db}"
    if kind == "gitlab":
        return str(options.get("base_url") or EMPTY)
    if kind == "rabbitmq":
        return str(options.get("management_url") or EMPTY)
    if kind == "kafka":
        server = _first(options.get("bootstrap_servers"))
        protocol = options.get("security_protocol") or "PLAINTEXT"
        return f"{server or EMPTY} · {protocol}"
    if kind == "cls":
        return str(options.get("region") or EMPTY)
    return EMPTY


def _scope(target: Target) -> tuple[str, dict[str, Any]]:
    options = target.options
    kind = target.type
    if kind == "mysql":
        dbs = options.get("allowed_dbs") or []
        return ("{count} 个库", {"count": len(dbs)}) if dbs else ("默认库", {})
    if kind in {"mongo", "elasticsearch"}:
        key = "allowed_dbs" if kind == "mongo" else "allowed_indices"
        items = options.get(key) or []
        source = "{count} 个库" if kind == "mongo" else "{count} 个索引"
        return (source, {"count": len(items)}) if items else ("未授权", {})
    if kind == "redis":
        prefix = options.get("key_prefix")
        return ("前缀 {prefix}", {"prefix": prefix}) if prefix else ("全部 key", {})
    if kind == "gitlab":
        items = options.get("allowed_projects") or []
        return ("{count} 个项目", {"count": len(items)}) if items else ("未授权", {})
    if kind == "rabbitmq":
        items = options.get("allowed_vhosts") or []
        return ("{count} 个 vhost", {"count": len(items)}) if items else ("未授权", {})
    if kind in {"kafka", "cls"}:
        items = options.get("allowed_topics") or []
        source = "{count} 个 topic" if kind == "kafka" else "{count} 个日志主题"
        return (source, {"count": len(items)}) if items else ("未授权", {})
    return ("—", {})


def to_view(target: Target) -> TargetView:
    spec = TYPE_SPECS.get(target.type)
    scope_source, scope_params = _scope(target)
    return TargetView(
        id=target.id,
        type=target.type,
        type_label=spec.label if spec else target.type,
        name=target.name,
        enabled=target.enabled,
        endpoint=_endpoint(target),
        scope=scope_source,
        scope_source=scope_source,
        scope_params=scope_params,
        secret_fields=tuple(sorted(target.secret_fields)),
        secret_ok=target.secret_ok,
        updated_at_display=_display_time(target.updated_at),
        last_test_at_display=_display_time(target.last_test_at),
        last_test_ok=target.last_test_ok,
        last_test_error=target.last_test_error,
    )


def list_views(targets: list[Target]) -> list[TargetView]:
    return [to_view(target) for target in targets]


def filter_views(
    views: list[TargetView], *, q: str = "", type_: str | None = None
) -> list[TargetView]:
    needle = q.strip().lower()
    filtered = views
    if type_:
        filtered = [view for view in filtered if view.type == type_]
    if needle:
        filtered = [
            view
            for view in filtered
            if needle
            in f"{view.name} {view.type} {view.type_label} {view.endpoint} {view.scope}".lower()
        ]
    return filtered


def stats(views: list[TargetView]) -> Stats:
    return Stats(
        total=len(views),
        enabled=sum(1 for view in views if view.enabled),
        failed=sum(1 for view in views if view.last_test_ok is False),
        key_issues=sum(
            1 for view in views if view.secret_fields and not view.secret_ok
        ),
    )
