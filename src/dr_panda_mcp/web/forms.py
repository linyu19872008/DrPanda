"""网页表单：字段定义、初值、解析与校验（planning 4.2 / 第 7 章）。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dr_panda_mcp.store.protocol import SecretPatch, Target, TargetDraft

NAME_PATTERN_HINT = "只允许小写字母、数字与连字符，以字母或数字开头结尾，最长 64"

COMMON_FIELDS = (
    ("timeout_s", "超时（秒）", 15, (1, 120)),
    ("max_rows", "单次行数上限", 100, (1, 1000)),
    ("max_bytes", "单次字节上限", 102_400, (4096, 1_048_576)),
)


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str  # text | int | bool | list | select
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    help: str = ""


@dataclass(frozen=True)
class SecretField:
    key: str
    label: str
    required: bool = False
    help: str = ""


@dataclass(frozen=True)
class TypeSpec:
    type: str
    label: str
    options: tuple[Field, ...]
    secrets: tuple[SecretField, ...]
    note: str = ""


TYPE_SPECS: dict[str, TypeSpec] = {
    "mysql": TypeSpec(
        "mysql",
        "MySQL",
        (
            Field("host", "主机", "text", required=True),
            Field("port", "端口", "int", default=3306),
            Field("user", "用户", "text", required=True),
            Field("default_db", "默认库", "text", required=True),
            Field("allowed_dbs", "允许的库（一行一个，空=只允许默认库）", "list"),
            Field("ssl", "启用 SSL", "bool", default=False),
        ),
        (SecretField("password", "密码", required=True),),
        "只允许单条 SELECT / SHOW / DESCRIBE / EXPLAIN；连接后强制事务只读。",
    ),
    "mongo": TypeSpec(
        "mongo",
        "Mongo",
        (
            Field("host", "主机", "text"),
            Field("port", "端口", "int", default=27017),
            Field("user", "用户", "text"),
            Field("auth_source", "认证库", "text", default="admin"),
            Field("allowed_dbs", "允许的库（一行一个，必须显式列）", "list", required=True),
        ),
        (
            SecretField("uri", "连接 URI（含凭证，留空则用主机方式）"),
            SecretField("password", "密码"),
        ),
        "find 必须带过滤条件；聚合只允许读阶段且 $group / $lookup 前要有 $match。",
    ),
    "elasticsearch": TypeSpec(
        "elasticsearch",
        "Elasticsearch",
        (
            Field("hosts", "地址列表（一行一个）", "list", required=True),
            Field("username", "用户名", "text"),
            Field("allowed_indices", "允许的索引（一行一个）", "list", required=True),
            Field("verify_tls", "校验 TLS", "bool", default=True),
        ),
        (
            SecretField("password", "密码"),
            SecretField("api_key", "API Key（与用户名密码二选一）"),
        ),
        "只发 GET / HEAD 与 _search / _count 的 POST；拒绝脚本与深分页。",
    ),
    "redis": TypeSpec(
        "redis",
        "Redis",
        (
            Field("host", "主机", "text", required=True),
            Field("port", "端口", "int", default=6379),
            Field("db", "DB", "int", default=0),
            Field("tls", "启用 TLS", "bool", default=False),
            Field("key_prefix", "key 前缀（空=不限）", "text"),
        ),
        (SecretField("password", "密码"),),
        "命令白名单；无界范围与全键命令一律拒绝。",
    ),
    "gitlab": TypeSpec(
        "gitlab",
        "GitLab",
        (
            Field("base_url", "实例地址", "text", required=True),
            Field("allowed_projects", "允许的项目（一行一个）", "list", required=True),
        ),
        (SecretField("token", "私人 Token", required=True),),
        "只发 GET；Token 权限再大也不会写。",
    ),
    "rabbitmq": TypeSpec(
        "rabbitmq",
        "RabbitMQ",
        (
            Field("management_url", "Management 地址", "text", required=True),
            Field("user", "用户", "text", required=True),
            Field("allowed_vhosts", "允许的 vhost（一行一个）", "list", required=True),
        ),
        (SecretField("password", "密码", required=True),),
        "只走 Management API 的 GET，不取消息。",
    ),
    "kafka": TypeSpec(
        "kafka",
        "Kafka",
        (
            Field("bootstrap_servers", "bootstrap 地址（一行一个）", "list", required=True),
            Field(
                "security_protocol",
                "安全协议",
                "select",
                default="PLAINTEXT",
                choices=("PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"),
            ),
            Field("sasl_mechanism", "SASL 机制", "text"),
            Field("sasl_user", "SASL 用户", "text"),
            Field("allowed_topics", "允许的 topic（一行一个）", "list", required=True),
        ),
        (SecretField("sasl_password", "SASL 密码"),),
        "只做描述类接口与保留范围内的有限拉取，不加入消费组。",
    ),
    "cls": TypeSpec(
        "cls",
        "CLS",
        (
            Field("region", "地域", "text", required=True),
            Field("allowed_topics", "允许的日志主题（一行一个，日志集/topic）", "list", required=True),
            Field("default_window_minutes", "默认时间窗（分钟）", "int", default=60),
            Field("max_window_minutes", "最大时间窗（分钟）", "int", default=1440),
        ),
        (
            SecretField("secret_id", "SecretId", required=True),
            SecretField("secret_key", "SecretKey", required=True),
        ),
        "搜索必须带时间窗，单次不超过 24 小时。",
    ),
}

TYPE_ORDER = tuple(TYPE_SPECS)


def spec_for(type_: str) -> TypeSpec | None:
    return TYPE_SPECS.get(type_)


def type_options() -> list[tuple[str, str]]:
    return [(spec.type, spec.label) for spec in TYPE_SPECS.values()]


def initial_values(spec: TypeSpec, target: Target | None = None) -> dict[str, str]:
    """新建用默认值；编辑用库里的 options。"""
    values: dict[str, str] = {
        "name": target.name if target else "",
        "enabled": "on" if (target is None or target.enabled) else "",
    }
    options = target.options if target else {}
    for field in spec.options:
        current = options.get(field.key, field.default)
        values[field.key] = _as_text(field, current)
    for key, _label, default, _ranges in COMMON_FIELDS:
        values[key] = str(options.get(key, default))
    return values


def parse_form(
    form: Mapping[str, Any],
    *,
    spec: TypeSpec,
    mode: str,
    existing: Target | None = None,
) -> tuple[TargetDraft | None, dict[str, str], dict[str, str]]:
    """解析并校验表单。返回 ``(draft, errors, values)``；有错误时 draft 为 None。"""
    errors: dict[str, str] = {}
    values = initial_values(spec, existing)

    name = existing.name if existing else _text(form, "name")
    values["name"] = name
    values["enabled"] = "on" if _checked(form, "enabled") else ""
    if not existing and not name:
        errors["name"] = "名称不能为空"

    options: dict[str, Any] = {}
    for field in spec.options:
        raw = _raw(form, field.key)
        values[field.key] = raw if field.kind != "bool" else ("on" if _checked(form, field.key) else "")
        parsed, error = _parse_field(field, raw, form)
        if error:
            errors[field.key] = error
        elif parsed is not None:
            options[field.key] = parsed

    for key, _label, default, (low, high) in COMMON_FIELDS:
        raw = _raw(form, key)
        values[key] = raw
        parsed, error = _parse_int(raw, low, high)
        if error:
            errors[key] = f"{key} 必须是 {low}–{high} 的整数"
        else:
            options[key] = parsed if parsed is not None else default

    secrets_set: dict[str, str] = {}
    secrets_clear: set[str] = set()
    for secret in spec.secrets:
        raw = _raw(form, f"secret_{secret.key}").strip()
        if raw:
            secrets_set[secret.key] = raw
        elif _checked(form, f"clear_{secret.key}"):
            secrets_clear.add(secret.key)
        elif mode == "create" and secret.required:
            errors[f"secret_{secret.key}"] = f"{secret.label}不能为空"

    _cross_validate(spec, options, secrets_set, secrets_clear, existing, errors, form)

    if errors:
        return None, errors, values

    draft = TargetDraft(
        name=name,
        type=spec.type,
        enabled=values["enabled"] == "on",
        options=options,
        secret_patch=SecretPatch(set=secrets_set, clear=frozenset(secrets_clear)),
    )
    return draft, {}, values


def _cross_validate(
    spec: TypeSpec,
    options: Mapping[str, Any],
    secrets_set: Mapping[str, str],
    secrets_clear: set[str],
    existing: Target | None,
    errors: dict[str, str],
    form: Mapping[str, Any],
) -> None:
    if spec.type == "mongo":
        has_uri = bool(secrets_set.get("uri")) or bool(
            existing and "uri" in existing.secret_fields and "uri" not in secrets_clear
        )
        if not has_uri and not options.get("host"):
            errors["host"] = "Mongo 需要填写连接 URI 或主机"
    if spec.type == "elasticsearch":
        password = secrets_set.get("password") or (
            existing and "password" in existing.secret_fields and "password" not in secrets_clear
        )
        api_key = secrets_set.get("api_key") or (
            existing and "api_key" in existing.secret_fields and "api_key" not in secrets_clear
        )
        has_user_auth = bool(options.get("username")) and bool(password)
        if has_user_auth == bool(api_key):
            errors["_form"] = "Elasticsearch 需要「用户名 + 密码」或 API Key，二选一"
    if spec.type == "kafka":
        protocol = str(options.get("security_protocol", "PLAINTEXT"))
        if protocol.startswith("SASL") and not options.get("sasl_mechanism"):
            errors["sasl_mechanism"] = "SASL 协议需要填写 SASL 机制"
    if spec.type == "cls":
        default_window = options.get("default_window_minutes")
        max_window = options.get("max_window_minutes")
        if isinstance(default_window, int) and isinstance(max_window, int):
            if default_window > max_window:
                errors["default_window_minutes"] = "默认时间窗不能大于最大时间窗"
            if not 1 <= max_window <= 1440:
                errors["max_window_minutes"] = "最大时间窗必须在 1–1440 分钟"


def _parse_field(field: Field, raw: str, form: Mapping[str, Any]) -> tuple[Any, str | None]:
    if field.kind == "int":
        parsed, error = _parse_int(raw, 1, 65535) if "port" in field.key else _parse_int(raw, 0, 1_000_000)
        if error:
            return None, f"{field.label}必须是整数"
        return (parsed if parsed is not None else field.default), None
    if field.kind == "bool":
        return _checked(form, field.key), None
    if field.kind == "list":
        items = [line.strip() for line in raw.splitlines() if line.strip()]
        return list(dict.fromkeys(items)), None
    if field.kind == "select":
        value = raw.strip() or field.default
        if field.choices and value not in field.choices:
            return None, f"{field.label}必须是 {', '.join(field.choices)} 之一"
        return value, None
    value = raw.strip()
    if field.required and not value:
        return None, f"{field.label}不能为空"
    return (value or None), None


def _parse_int(raw: str, low: int, high: int) -> tuple[int | None, str | None]:
    if not raw or not str(raw).strip():
        return None, None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None, "不是整数"
    if not low <= value <= high:
        return None, "超出范围"
    return value, None


def _raw(form: Mapping[str, Any], key: str) -> str:
    value = form.get(key)
    return "" if value is None else str(value)


def _text(form: Mapping[str, Any], key: str) -> str:
    return _raw(form, key).strip()


def _checked(form: Mapping[str, Any], key: str) -> bool:
    return form.get(key) is not None


def _as_text(field: Field, value: Any) -> str:
    if value is None:
        return ""
    if field.kind == "bool":
        return "on" if value else ""
    if field.kind == "list":
        if isinstance(value, (list, tuple)):
            return "\n".join(str(item) for item in value)
        return str(value)
    return str(value)


def option_rows(
    spec: TypeSpec,
    values: Mapping[str, str],
    errors: Mapping[str, str],
) -> list[dict[str, Any]]:
    rows = []
    for field in spec.options:
        rows.append(
            {
                "key": field.key,
                "label": field.label,
                "kind": field.kind,
                "value": values.get(field.key, ""),
                "error": errors.get(field.key),
                "choices": field.choices,
                "required": field.required,
                "help": field.help,
            }
        )
    return rows


def secret_rows(
    spec: TypeSpec,
    errors: Mapping[str, str],
    existing: Target | None,
) -> list[dict[str, Any]]:
    rows = []
    for secret in spec.secrets:
        has_value = bool(existing and secret.key in existing.secret_fields)
        rows.append(
            {
                "key": secret.key,
                "label": secret.label,
                "required": secret.required,
                "has_value": has_value,
                "error": errors.get(f"secret_{secret.key}"),
                "help": secret.help,
            }
        )
    return rows


def common_rows(values: Mapping[str, str], errors: Mapping[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": label,
            "value": values.get(key, str(default)),
            "error": errors.get(key),
            "help": f"范围 {low}–{high}",
        }
        for key, label, default, (low, high) in COMMON_FIELDS
    ]
