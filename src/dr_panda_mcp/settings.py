"""系统配置的默认值、键白名单与范围校验（planning 4.5 / 5.2）。

配置库只存字符串；合法性由这里负责。读取时遇到非法值回退默认并记 WARNING。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from dr_panda_mcp.errors import InvalidSettings
from dr_panda_mcp.store.protocol import ConfigStore, Settings

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, int] = {
    "audit_retention_days": 90,
    "target_max_concurrency": 10,
}

RANGES: dict[str, tuple[int, int]] = {
    "audit_retention_days": (1, 3650),
    "target_max_concurrency": (1, 50),
}

SETTING_KEYS = frozenset(DEFAULTS)


def validate_patch(patch: Mapping[str, object]) -> dict[str, str]:
    """校验提交的配置项，返回规范化后的字符串值；非法时抛 ``InvalidSettings``。"""
    if not patch:
        raise InvalidSettings("没有需要保存的系统配置")

    normalized: dict[str, str] = {}
    for key, raw in patch.items():
        if key not in DEFAULTS:
            raise InvalidSettings(f"未知的系统配置键：{key}")
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError) as exc:
            raise InvalidSettings(f"{key} 必须是整数，当前：{raw!r}") from exc
        low, high = RANGES[key]
        if not low <= value <= high:
            raise InvalidSettings(f"{key} 必须在 {low}–{high} 之间，当前：{value}")
        normalized[key] = str(value)
    return normalized


def _coerce(key: str, raw: object) -> int | None:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    low, high = RANGES[key]
    return value if low <= value <= high else None


async def load(store: ConfigStore) -> Settings:
    """读取系统配置；缺失或非法的键回退到默认值。"""
    raw = await store.get_settings()
    values: dict[str, int] = {}
    for key, default in DEFAULTS.items():
        if key not in raw:
            values[key] = default
            continue
        parsed = _coerce(key, raw[key])
        if parsed is None:
            logger.warning(
                "系统配置 %s=%r 不合法，已回退默认值 %s", key, raw[key], default
            )
            parsed = default
        values[key] = parsed
    return Settings(
        audit_retention_days=values["audit_retention_days"],
        target_max_concurrency=values["target_max_concurrency"],
    )


async def update(store: ConfigStore, patch: Mapping[str, object], actor: str) -> Settings:
    """校验并保存配置，随后返回生效值。"""
    normalized = validate_patch(patch)
    await store.update_settings(normalized, actor)
    return await load(store)
