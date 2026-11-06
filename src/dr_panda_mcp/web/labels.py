"""展示层标签：错误码 → 中文短标签。

只影响网页显示（`UPSTREAM_UNAVAILABLE（上游不可达）` 形式），不改变 MCP 工具返回的
``CODE: message`` 契约，也不改审计数据；未知错误码原样回退。
"""

from __future__ import annotations

from dr_panda_mcp import errors

ERROR_LABELS: dict[str, str] = {
    errors.TARGET_NOT_FOUND: "目标不存在",
    errors.TARGET_DISABLED: "目标已停用",
    errors.TARGET_TYPE_MISMATCH: "目标类型不匹配",
    errors.NO_ENABLED_TARGET: "没有启用的目标",
    errors.ENVIRONMENT_REQUIRED: "需要指定环境",
    errors.ENVIRONMENT_NOT_FOUND: "环境不存在",
    errors.ENVIRONMENT_DISABLED: "环境已停用",
    errors.INVALID_ARGUMENT: "参数不合法",
    errors.GUARD_REJECTED: "被只读规则拒绝",
    errors.DANGEROUS_OPERATION: "危险操作被拒绝",
    errors.SCOPE_DENIED: "超出授权范围",
    errors.UPSTREAM_NOT_FOUND: "上游记录不存在",
    errors.UPSTREAM_TIMEOUT: "上游超时",
    errors.UPSTREAM_UNAVAILABLE: "上游不可达",
    errors.UPSTREAM_QUERY_ERROR: "上游拒绝查询",
    errors.UPSTREAM_AUTH: "上游认证失败",
    errors.STORAGE_UNAVAILABLE: "配置库不可用",
    errors.SECRET_UNAVAILABLE: "密钥不可用",
    errors.INTERNAL: "服务内部错误",
}

# 中文源文案；en.json 里给英文用半角括号。
ERROR_CODE_DISPLAY = "{code}（{label}）"


def error_label(code: str) -> str:
    return ERROR_LABELS.get(code, code)
