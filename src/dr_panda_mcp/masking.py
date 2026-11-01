"""脱敏：密钥、手机号、证件号与常见凭证字样（planning 5.4）。

用于把上游错误摘要、审计 summary 落盘或展示前的清理；不做加密。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_CARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_CREDENTIAL = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)\b\s*[=:]\s*[^\s,;]+"
)


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """按密钥字面量与常见敏感格式做打码；``text`` 为空时返回空串。"""
    if not text:
        return ""
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, "***")
    result = _PHONE.sub("1**********", result)
    result = _ID_CARD.sub(lambda match: match.group(0)[:6] + "********" + match.group(0)[-4:], result)
    result = _CREDENTIAL.sub(lambda match: f"{match.group(1)}=***", result)
    return result
