"""MCP prompt：investigate_error（planning 8.7）。"""

from __future__ import annotations

from fastmcp import FastMCP

PROMPT_NAME = "investigate_error"

_TEMPLATE = """你是线上故障排查助手。全部工具只读，不能修改任何线上状态。

已知信息：
{context}

排查顺序：
1. 先用 systems_status 确认哪些目标已登记、已启用、最近是否连通。
2. 需要写查询前先看结构：MySQL 用 mysql_tables、mysql_describe，Mongo 用 mongo_collections，Elasticsearch 用 es_mapping。不要凭猜写表名和字段名。
3. 有 trace id 时先 cls_search 按 trace id + 时间窗检索；没有就按服务名与时间窗检索。
4. 用异常类名、堆栈或日志原文调用 gitlab_search_code；命中后用 gitlab_get_file 读代码，gitlab_blame 看最近改动。
5. 现象像慢查询或数据不一致，走 mysql_explain、mysql_query；缓存放 redis_get、redis_scan、redis_info；搜索放 es_search、es_health。
6. 现象像堆积或延迟，走 rabbit_queues、kafka_lag、kafka_peek。
7. 结论必须写明时间窗、目标与证据（具体条目）；结果被截断要说明。
8. 证据不足就明确说缺什么，不猜、不编造行号与数值。
9. 全程只读，不尝试写操作。"""


def register_prompts(server: FastMCP) -> None:
    @server.prompt(
        name=PROMPT_NAME,
        description="按日志→代码→数据/消息的顺序排查线上报错，全程只读",
    )
    def investigate_error(
        description: str = "",
        service: str = "",
        trace_id: str = "",
        time_range: str = "",
    ) -> str:
        """把推荐排查顺序与已知信息交给模型。"""
        lines: list[str] = []
        if description:
            lines.append(f"- 现象：{description}")
        if service:
            lines.append(f"- 服务：{service}")
        if trace_id:
            lines.append(f"- trace id：{trace_id}")
        if time_range:
            lines.append(f"- 时间窗：{time_range}")
        context = "\n".join(lines) if lines else "（调用方未提供，先向用户确认现象、服务与时间窗）"
        return _TEMPLATE.format(context=context)
