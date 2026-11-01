"""错误码与异常基类。

错误码是对外契约的一部分（planning 8.2），工具失败时以 ``CODE: message`` 形式返回；
内部一律用异常传递。M0 只落地常量与基础异常，ToolError 映射在 M2 接入。
"""

from __future__ import annotations

# 目标相关
TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
TARGET_DISABLED = "TARGET_DISABLED"
TARGET_TYPE_MISMATCH = "TARGET_TYPE_MISMATCH"
NO_ENABLED_TARGET = "NO_ENABLED_TARGET"

# 参数与闸门
INVALID_ARGUMENT = "INVALID_ARGUMENT"
GUARD_REJECTED = "GUARD_REJECTED"
DANGEROUS_OPERATION = "DANGEROUS_OPERATION"
SCOPE_DENIED = "SCOPE_DENIED"

# 上游
UPSTREAM_NOT_FOUND = "UPSTREAM_NOT_FOUND"
UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"

# 本服务自身
STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
SECRET_UNAVAILABLE = "SECRET_UNAVAILABLE"
INTERNAL = "INTERNAL"

ALL_CODES = frozenset(
    {
        TARGET_NOT_FOUND,
        TARGET_DISABLED,
        TARGET_TYPE_MISMATCH,
        NO_ENABLED_TARGET,
        INVALID_ARGUMENT,
        GUARD_REJECTED,
        DANGEROUS_OPERATION,
        SCOPE_DENIED,
        UPSTREAM_NOT_FOUND,
        UPSTREAM_TIMEOUT,
        UPSTREAM_UNAVAILABLE,
        STORAGE_UNAVAILABLE,
        SECRET_UNAVAILABLE,
        INTERNAL,
    }
)


class DrPandaError(Exception):
    """本服务所有可预期异常的基类。"""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class ConfigError(DrPandaError):
    """环境变量或启动配置不合法，进程应以非零码退出。"""


class StartupError(DrPandaError):
    """启动过程中不可继续的错误（端口占用、迁移失败等）。"""


class TargetNotFound(DrPandaError):
    """按名字或 id 找不到目标。"""


class TargetNameTaken(DrPandaError):
    """目标名已被占用（唯一约束）。"""


class InvalidTarget(DrPandaError):
    """目标字段不合法，或试图修改不可变字段。"""


class StorageUnavailable(DrPandaError):
    """配置库不可用。"""


class SecretUnavailable(DrPandaError):
    """密钥无法解密（密钥缺失、被替换或密文损坏）。"""


class InvalidSettings(DrPandaError):
    """系统配置键或取值不合法。"""


class ScopeDenied(DrPandaError):
    """请求超出该目标授权的范围（库/索引/topic/项目/vhost）。"""


class InvalidArgument(DrPandaError):
    """工具参数不合法（缺失、越界、时间窗超限等）。"""


class TargetDisabled(DrPandaError):
    """目标已停用，工具拒绝使用。"""


class TargetTypeMismatch(DrPandaError):
    """目标的类型与调用的工具不一致。"""


class GuardRejected(DrPandaError):
    """只读白名单或危险清单拒绝了请求（code 取 ``GUARD_REJECTED`` / ``DANGEROUS_OPERATION``）。"""


class UpstreamError(DrPandaError):
    """排查目标（上游系统）返回错误或不可用。"""


class UpstreamTimeout(UpstreamError):
    """上游调用超时。"""


class UpstreamUnavailable(UpstreamError):
    """上游连接失败或返回 5xx。"""


class UpstreamNotFound(UpstreamError):
    """上游返回 404（库、索引、文件不存在）。"""
