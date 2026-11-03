"""系统配置的默认值、范围、分组与校验（planning 4.5 / 5.2）。

配置库只存字符串；合法性由这里负责。读取时遇到非法值回退默认并记 WARNING。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from dr_panda_mcp.errors import InvalidSettings
from dr_panda_mcp.store.protocol import ConfigStore, Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SettingSpec:
    key: str
    group: str
    label: str
    unit: str
    default: int
    low: int
    high: int
    effect: str
    help: str
    subgroup: str = ""


SETTING_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec(
        "default_target_timeout_s",
        "target_defaults",
        "默认超时",
        "秒",
        15,
        1,
        120,
        "仅新建目标",
        "新建目标表单的默认 timeout_s；既有目标仍使用各自配置。",
    ),
    SettingSpec(
        "default_target_max_rows",
        "target_defaults",
        "默认行数上限",
        "行",
        100,
        1,
        1000,
        "仅新建目标",
        "新建目标表单的默认 max_rows；既有目标仍使用各自配置。",
    ),
    SettingSpec(
        "default_target_max_bytes",
        "target_defaults",
        "默认字节上限",
        "字节",
        102_400,
        4096,
        1_048_576,
        "仅新建目标",
        "新建目标表单的默认 max_bytes；既有目标仍使用各自配置。",
    ),
    SettingSpec(
        "target_max_concurrency",
        "runtime",
        "每 target 并发上限",
        "个",
        10,
        1,
        50,
        "下一次取槽",
        "同一个目标同时进行的工具调用上限，超出会排队。已经在跑的调用不会被取消。",
        "并发控制",
    ),
    SettingSpec(
        "audit_retention_days",
        "runtime",
        "审计保留天数",
        "天",
        90,
        1,
        3650,
        "下一轮清理",
        "超过该天数的审计记录会被定时清理；清理只记日志。",
        "审计维护",
    ),
    SettingSpec(
        "catalog_max_clients",
        "advanced",
        "连接器缓存上限",
        "个",
        32,
        4,
        128,
        "下一次工具调用",
        "进程内缓存的连接器客户端数量；修改后在下一次取客户端时按新上限淘汰。",
    ),
    SettingSpec(
        "session_ttl_minutes",
        "auth",
        "Session 有效期",
        "分钟",
        720,
        30,
        10080,
        "下一次请求",
        "Web 登录会话的最长有效期，最短 30 分钟。缩短后，已超过新时长的会话在下一次请求失效；使用中的会话会按当前时长续期。",
    ),
    SettingSpec(
        "backup_keep_count",
        "advanced",
        "SQLite 备份保留数量",
        "个",
        20,
        1,
        20,
        "下一次启动迁移",
        "仅 SQLite 且存在 pending migration 时生效；新迁移前保留最近 N 个备份。",
    ),
    SettingSpec(
        "audit_cleanup_interval_minutes",
        "runtime",
        "审计清理间隔",
        "分钟",
        60,
        5,
        1440,
        "下一轮清理",
        "每轮清理后按该间隔休眠；修改后下一轮开始使用新值。",
        "审计维护",
    ),
)

SETTING_GROUPS: tuple[dict[str, str], ...] = (
    {
        "key": "target_defaults",
        "title": "新建目标默认值",
        "description": "只影响新建目标表单；既有目标保留各自已保存的 timeout / 行数 / 字节设置。",
    },
    {
        "key": "runtime",
        "title": "并发与审计",
        "description": "并发上限在下一次取槽生效；已经在跑的调用不会被取消。审计留存与清理间隔在下一轮清理周期生效。",
    },
    {
        "key": "auth",
        "title": "认证与会话",
        "description": "Web 登录会话有效期。缩短后，已超过新时长的会话在下一次请求失效；使用中的会话会按当前时长续期。",
    },
    {
        "key": "advanced",
        "title": "高级资源",
        "description": "连接器缓存在下一次取客户端时生效。SQLite 备份份数只在下次启动迁移前生效。",
    },
)

DEFAULTS: dict[str, int] = {spec.key: spec.default for spec in SETTING_SPECS}
RANGES: dict[str, tuple[int, int]] = {
    spec.key: (spec.low, spec.high) for spec in SETTING_SPECS
}
SPEC_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SETTING_SPECS}
SETTING_KEYS = frozenset(DEFAULTS)


def rows_specs() -> tuple[SettingSpec, ...]:
    return SETTING_SPECS


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
            label = SPEC_BY_KEY[key].label
            raise InvalidSettings(f"{label} 必须是整数，当前：{raw!r}") from exc
        low, high = RANGES[key]
        if not low <= value <= high:
            label = SPEC_BY_KEY[key].label
            raise InvalidSettings(
                f"{label} 必须在 {low}–{high} 之间，当前：{value}"
            )
        normalized[key] = str(value)
    return normalized


def _coerce(key: str, raw: object) -> int | None:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    low, high = RANGES[key]
    return value if low <= value <= high else None


def target_form_defaults(current: Settings) -> dict[str, int]:
    """新建目标表单使用的全局默认值。"""
    return {
        "timeout_s": current.default_target_timeout_s,
        "max_rows": current.default_target_max_rows,
        "max_bytes": current.default_target_max_bytes,
    }


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
        default_target_timeout_s=values["default_target_timeout_s"],
        default_target_max_rows=values["default_target_max_rows"],
        default_target_max_bytes=values["default_target_max_bytes"],
        audit_cleanup_interval_minutes=values["audit_cleanup_interval_minutes"],
        catalog_max_clients=values["catalog_max_clients"],
        backup_keep_count=values["backup_keep_count"],
        session_ttl_minutes=values["session_ttl_minutes"],
    )


async def update(store: ConfigStore, patch: Mapping[str, object], actor: str) -> Settings:
    """校验并保存配置，随后返回生效值。"""
    normalized = validate_patch(patch)
    await store.update_settings(normalized, actor)
    return await load(store)
