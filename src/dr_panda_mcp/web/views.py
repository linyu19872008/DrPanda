"""网页视图模型：把 Target 转成不含密钥的展示数据（planning 4.3 / 5.2）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from dr_panda_mcp.store.protocol import Target
from dr_panda_mcp.web.forms import TYPE_SPECS


@dataclass(frozen=True)
class TargetView:
    id: int
    type: str
    type_label: str
    name: str
    enabled: bool
    secret_fields: tuple[str, ...]
    secret_ok: bool
    updated_at: str | None
    last_test_at: str | None
    last_test_ok: bool | None
    last_test_error: str | None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value is not None else None


def to_view(target: Target) -> TargetView:
    spec = TYPE_SPECS.get(target.type)
    return TargetView(
        id=target.id,
        type=target.type,
        type_label=spec.label if spec else target.type,
        name=target.name,
        enabled=target.enabled,
        secret_fields=tuple(sorted(target.secret_fields)),
        secret_ok=target.secret_ok,
        updated_at=_iso(target.updated_at),
        last_test_at=_iso(target.last_test_at),
        last_test_ok=target.last_test_ok,
        last_test_error=target.last_test_error,
    )


def grouped(targets: list[Target]) -> list[dict]:
    """按类型分组，保持表单里的类型顺序；空组不出现。"""
    views = [to_view(target) for target in targets]
    groups: list[dict] = []
    for type_, spec in TYPE_SPECS.items():
        members = [view for view in views if view.type == type_]
        if members:
            groups.append({"type": type_, "label": spec.label, "targets": members})
    return groups
