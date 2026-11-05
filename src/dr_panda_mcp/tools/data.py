"""数据面：MySQL / Mongo / Elasticsearch / Redis 十七个只读工具（planning 8.5）。"""

from __future__ import annotations

import json
import re
import time
from typing import Annotated, Any

import sqlglot
from fastmcp import FastMCP
from pydantic import Field
from sqlglot import exp

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base as connectors_base
from dr_panda_mcp.connectors import get_connector
from dr_panda_mcp.guards import es as es_guard
from dr_panda_mcp.guards import mongo as mongo_guard
from dr_panda_mcp.guards import mysql as mysql_guard
from dr_panda_mcp.guards import redis as redis_guard
from dr_panda_mcp.guards.protocol import require
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.protocol import Target
from dr_panda_mcp.tools.base import (
    TOOL_ANNOTATIONS,
    EnvironmentParam,
    clamp_limit,
    finish,
    run_tool,
    trim_rows,
)


def _items(target: Target, key: str) -> list[str]:
    values = target.options.get(key, [])
    return [str(item) for item in values]


def ensure_processlist_allowed(target: Target) -> None:
    if not target.options.get("allow_processlist"):
        raise errors.ScopeDenied(
            f"目标 {target.name} 未启用 PROCESSLIST；该命令可能暴露其他库/用户的会话"
        )


def ensure_mongo_collection(target: Target, collection: str) -> str:
    value = (collection or "").strip()
    if not value:
        raise errors.InvalidArgument("collection 不能为空")
    if value.lower().startswith("system."):
        raise errors.ScopeDenied(f"不允许访问系统集合 {value}")
    return value


def ensure_db(target: Target, db: str) -> str:
    allowed = _items(target, "allowed_dbs")
    default = str(target.options.get("default_db") or "")
    value = (db or "").strip() or default
    if not value:
        raise errors.InvalidArgument("必须指定 db（目标未配置 default_db）")
    if value not in allowed:
        raise errors.ScopeDenied(f"库 {value} 不在目标 {target.name} 的授权范围内")
    return value


def ensure_index(target: Target, index: str) -> str:
    allowed = _items(target, "allowed_indices")
    value = (index or "").strip()
    if not value:
        raise errors.InvalidArgument("必须指定 index")
    if value not in allowed:
        raise errors.ScopeDenied(f"索引 {value} 不在目标 {target.name} 的授权范围内")
    return value


def ensure_key(target: Target, key: str) -> str:
    value = (key or "").strip()
    if not value:
        raise errors.InvalidArgument("key 不能为空")
    prefix = str(target.options.get("key_prefix") or "")
    if prefix and not value.startswith(prefix):
        raise errors.ScopeDenied(f"key 必须以 {prefix} 开头")
    return value


def _json_object(text: str, name: str, *, required: bool) -> dict[str, Any]:
    if not (text or "").strip():
        if required:
            raise errors.InvalidArgument(f"{name} 不能为空")
        return {}
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise errors.InvalidArgument(f"{name} 不是合法 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise errors.InvalidArgument(f"{name} 必须是 JSON 对象")
    return value


def _json_array(text: str, name: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise errors.InvalidArgument(f"{name} 不是合法 JSON：{exc}") from exc
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise errors.InvalidArgument(f"{name} 必须是对象数组")
    return value


def _quote(identifier: str) -> str:
    return "`" + identifier.replace("`", "``") + "`"


_EXPLAIN_PREFIX = re.compile(r"^\s*EXPLAIN\b\s*", re.IGNORECASE)


def _explain_inner(sql: str) -> str:
    """``sql`` 允许自带 EXPLAIN 前缀；工具内部统一只拼一次。"""
    return _EXPLAIN_PREFIX.sub("", sql.strip(), count=1).strip()


def _mysql_scope(target: Target, sql: str, default_db: str) -> None:
    """库级范围：所有表/库引用必须在 allowed_dbs 内；禁止 SHOW DATABASES。"""
    expression = sqlglot.parse_one(sql, dialect=mysql_guard.DIALECT)
    if isinstance(expression, exp.Show):
        command = str(expression.this or "").upper()
        if command == "DATABASES":
            raise errors.ScopeDenied("不允许在目标级查询所有数据库")
        db = expression.args.get("db")
        if db is not None and str(db.name).lower() not in {
            item.lower() for item in _items(target, "allowed_dbs")
        }:
            raise errors.ScopeDenied(f"库 {db.name} 不在目标 {target.name} 的授权范围内")
        return
    inner = expression.this if isinstance(expression, exp.Describe) else expression
    allowed = set(_items(target, "allowed_dbs"))
    for table in inner.find_all(exp.Table):
        db = (table.db or default_db).lower()
        if db and db not in {item.lower() for item in allowed}:
            raise errors.ScopeDenied(f"库 {db} 不在目标 {target.name} 的授权范围内")


def force_limit(sql: str, cap: int) -> str:
    expression = sqlglot.parse_one(sql, dialect=mysql_guard.DIALECT)
    if isinstance(expression, exp.Select):
        existing = expression.args.get("limit")
        if existing is not None:
            try:
                current = int(existing.expression.this)
            except (AttributeError, TypeError, ValueError):
                current = None
            if current is not None and current <= cap:
                # 用户已经写了更小的 LIMIT，不要擅自放大。
                return expression.sql(dialect=mysql_guard.DIALECT)
        return expression.limit(cap).sql(dialect=mysql_guard.DIALECT)
    return sql


def _slowlog_matches(entry: dict[str, Any], prefix: str) -> bool:
    """慢日志条目里至少有一个参数以 key 前缀开头才允许返回。"""
    command = entry.get("command")
    if isinstance(command, str):
        tokens = command.split()
    elif isinstance(command, (list, tuple)):
        tokens = [str(token) for token in command]
    else:
        return False
    return any(token.startswith(prefix) for token in tokens[1:])


def _pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def register_data_tools(server: FastMCP, runtime: Runtime) -> None:
    # ------------------------------------------------------------------ MySQL
    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def mysql_tables(
        target: str, db: str = "", environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """列出授权库的表（名称、类型、行数估算、注释）。"""
        params = {"db": db or None}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_db(tgt, db)
            sql = f"SHOW TABLE STATUS FROM {_quote(chosen)}"
            require(mysql_guard.check_sql(sql))
            connector = get_connector("mysql")
            client = await runtime.catalog.client(tgt, connector)
            raw = await connector.fetch_rows(client, tgt, sql)
            rows = [
                {
                    "table": _pick(row, "Name"),
                    "type": "view"
                    if str(_pick(row, "Comment") or "").upper() == "VIEW"
                    else "base",
                    "rows": _pick(row, "Rows"),
                    "comment": _pick(row, "Comment"),
                }
                for row in raw
            ]
            return finish(
                tgt,
                summary=f"SHOW TABLE STATUS FROM {chosen}",
                started=started,
                rows=rows,
                stats={"db": chosen},
            )

        return await run_tool(
            runtime, tool="mysql_tables", name=target, environment=environment, target_type="mysql",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def mysql_describe(
        target: str, table: str, db: str = "", environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """查看表结构（字段与索引）。"""
        params = {"table": table, "db": db or None}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_db(tgt, db)
            if not table.strip():
                raise errors.InvalidArgument("table 不能为空")
            columns_sql = f"SHOW FULL COLUMNS FROM {_quote(table)} FROM {_quote(chosen)}"
            indexes_sql = f"SHOW INDEX FROM {_quote(table)} FROM {_quote(chosen)}"
            require(mysql_guard.check_sql(columns_sql))
            require(mysql_guard.check_sql(indexes_sql))
            connector = get_connector("mysql")
            client = await runtime.catalog.client(tgt, connector)
            raw_columns = await connector.fetch_rows(client, tgt, columns_sql)
            raw_indexes = await connector.fetch_rows(client, tgt, indexes_sql)
            rows = [
                {
                    "field": _pick(row, "Field"),
                    "type": _pick(row, "Type"),
                    "nullable": _pick(row, "Null"),
                    "key": _pick(row, "Key"),
                    "default": _pick(row, "Default"),
                    "extra": _pick(row, "Extra"),
                }
                for row in raw_columns
            ]
            indexes = [
                {
                    "name": _pick(row, "Key_name"),
                    "column": _pick(row, "Column_name"),
                    "unique": _pick(row, "Non_unique") == 0,
                    "type": _pick(row, "Index_type"),
                }
                for row in raw_indexes
            ]
            return finish(
                tgt,
                summary=f"SHOW FULL COLUMNS FROM {chosen}.{table}",
                started=started,
                rows=rows,
                stats={"db": chosen, "table": table, "indexes": indexes},
            )

        return await run_tool(
            runtime, tool="mysql_describe", name=target, environment=environment, target_type="mysql",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def mysql_query(
        target: str, sql: str, limit: int = 0, environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """执行单条只读 SQL（自动补 LIMIT）。"""
        params = {"sql": sql, "limit": limit or None}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            decision = require(mysql_guard.check_sql(sql))
            if decision.get("command") == "PROCESSLIST":
                ensure_processlist_allowed(tgt)
            default_db = ensure_db(tgt, "")
            _mysql_scope(tgt, sql, default_db)
            cap = clamp_limit(limit or None, tgt, connectors_base.max_rows(tgt))
            effective = force_limit(sql, cap + 1)
            connector = get_connector("mysql")
            client = await runtime.catalog.client(tgt, connector)
            fetched = await connector.fetch_rows(client, tgt, effective)
            rows, truncation = trim_rows(fetched, cap)
            return finish(
                tgt,
                summary=f"MySQL {decision.get('kind', 'read')} (limit={cap})",
                started=started,
                rows=rows,
                stats={"db": default_db, "limit": cap},
                truncation=truncation,
            )

        return await run_tool(
            runtime, tool="mysql_query", name=target, environment=environment, target_type="mysql",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def mysql_explain(
        target: str, sql: str, environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """查看 SELECT 的执行计划（sql 可带或不带 EXPLAIN 前缀；不使用 EXPLAIN ANALYZE）。"""
        params = {"sql": sql}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            inner = _explain_inner(sql)
            if not inner:
                raise errors.InvalidArgument("sql 不能为空")
            statement = f"EXPLAIN {inner}"
            require(mysql_guard.check_sql(statement))
            default_db = ensure_db(tgt, "")
            _mysql_scope(tgt, statement, default_db)
            connector = get_connector("mysql")
            client = await runtime.catalog.client(tgt, connector)
            rows = await connector.fetch_rows(client, tgt, statement)
            return finish(
                tgt,
                summary="EXPLAIN SELECT",
                started=started,
                rows=rows,
                stats={"db": default_db},
            )

        return await run_tool(
            runtime, tool="mysql_explain", name=target, environment=environment, target_type="mysql",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def mysql_processlist(
        target: str, environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """查看当前会话列表（SHOW PROCESSLIST）。"""
        params: dict[str, Any] = {}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            decision = require(mysql_guard.check_sql("SHOW PROCESSLIST"))
            if decision.get("command") == "PROCESSLIST":
                ensure_processlist_allowed(tgt)
            connector = get_connector("mysql")
            client = await runtime.catalog.client(tgt, connector)
            rows = await connector.fetch_rows(client, tgt, "SHOW PROCESSLIST")
            return finish(
                tgt, summary="SHOW PROCESSLIST", started=started, rows=rows
            )

        return await run_tool(
            runtime, tool="mysql_processlist", name=target, environment=environment, target_type="mysql",
            params=params, handler=handler,
        )

    # ------------------------------------------------------------------ Mongo
    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def mongo_collections(
        target: str, db: str, environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """列出库里的集合（文档数估算与索引数）。"""
        params = {"db": db}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_db(tgt, db)
            require(mongo_guard.check_mongo_command("listCollections", {}))
            connector = get_connector("mongo")
            client = await runtime.catalog.client(tgt, connector)
            cap = connectors_base.max_rows(tgt)
            fetched = await connector.collections(client, tgt, db=chosen, limit=cap + 1)
            fetched = [
                row
                for row in fetched
                if not str(row.get("collection", "")).lower().startswith("system.")
            ]
            rows, truncation = trim_rows(fetched, cap)
            return finish(
                tgt,
                summary=f"listCollections {chosen}",
                started=started,
                rows=rows,
                stats={"db": chosen},
                truncation=truncation,
            )

        return await run_tool(
            runtime, tool="mongo_collections", name=target, environment=environment, target_type="mongo",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def mongo_find(
        target: str,
        db: str,
        collection: str,
        filter: str,
        projection: str = "",
        sort: str = "",
        limit: int = 0,
        skip: int = 0,
        environment: EnvironmentParam = "",
    ) -> dict[str, Any]:
        """按过滤条件查询文档（filter 必填）。"""
        params = {
            "db": db, "collection": collection, "filter": filter,
            "projection": projection or None, "sort": sort or None,
            "limit": limit or None,
            "skip": skip or None,
        }

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_db(tgt, db)
            chosen_collection = ensure_mongo_collection(tgt, collection)
            if skip < 0:
                raise errors.InvalidArgument("skip 不能为负数")
            if skip > 10_000:
                raise errors.GuardRejected(
                    "skip 不能超过 10000，请缩小过滤条件",
                    code=errors.DANGEROUS_OPERATION,
                )
            filter_obj = _json_object(filter, "filter", required=True)
            projection_obj = _json_object(projection, "projection", required=False) or None
            sort_obj = _json_object(sort, "sort", required=False) or None
            require(
                mongo_guard.check_mongo_command(
                    "find",
                    {
                        "filter": filter_obj,
                        "projection": projection_obj,
                        "sort": sort_obj,
                    },
                )
            )
            cap = clamp_limit(limit or None, tgt, connectors_base.max_rows(tgt))
            connector = get_connector("mongo")
            client = await runtime.catalog.client(tgt, connector)
            fetched = await connector.find(
                client,
                tgt,
                db=chosen,
                collection=chosen_collection,
                filter_=filter_obj,
                projection=projection_obj,
                sort=sort_obj,
                limit=cap + 1,
                skip=skip,
            )
            rows, truncation = trim_rows(fetched, cap)
            return finish(
                tgt,
                summary=f"find {chosen}.{chosen_collection} (limit={cap}, skip={skip})",
                started=started,
                rows=rows,
                stats={
                    "db": chosen,
                    "collection": chosen_collection,
                    "limit": cap,
                    "skip": skip,
                },
                truncation=truncation,
            )

        return await run_tool(
            runtime, tool="mongo_find", name=target, environment=environment, target_type="mongo",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def mongo_aggregate(
        target: str,
        db: str,
        collection: str,
        pipeline: str,
        limit: int = 0,
        environment: EnvironmentParam = "",
    ) -> dict[str, Any]:
        """执行聚合管道（阶段白名单；自动补 $limit）。"""
        params = {"db": db, "collection": collection, "pipeline": pipeline, "limit": limit or None}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_db(tgt, db)
            chosen_collection = ensure_mongo_collection(tgt, collection)
            stages = _json_array(pipeline, "pipeline")
            require(mongo_guard.check_mongo_command("aggregate", {"pipeline": stages}))
            cap = clamp_limit(limit or None, tgt, connectors_base.max_rows(tgt))
            connector = get_connector("mongo")
            client = await runtime.catalog.client(tgt, connector)
            fetched = await connector.aggregate(
                client, tgt, db=chosen, collection=chosen_collection, pipeline=stages, limit=cap + 1
            )
            rows, truncation = trim_rows(fetched, cap)
            return finish(
                tgt,
                summary=f"aggregate {chosen}.{chosen_collection} (limit={cap})",
                started=started,
                rows=rows,
                stats={"db": chosen, "collection": chosen_collection, "limit": cap},
                truncation=truncation,
            )

        return await run_tool(
            runtime, tool="mongo_aggregate", name=target, environment=environment, target_type="mongo",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def mongo_stats(
        target: str,
        db: str,
        collection: str = "",
        environment: EnvironmentParam = "",
    ) -> dict[str, Any]:
        """查看集合或库的统计信息。"""
        params = {"db": db, "collection": collection or None}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_db(tgt, db)
            chosen_collection = (
                ensure_mongo_collection(tgt, collection) if collection else None
            )
            command = "collStats" if chosen_collection else "dbStats"
            require(mongo_guard.check_mongo_command(command, {}))
            connector = get_connector("mongo")
            client = await runtime.catalog.client(tgt, connector)
            rows = await connector.stats(
                client, tgt, db=chosen, collection=chosen_collection
            )
            return finish(
                tgt,
                summary=f"{command} {chosen}"
                + (f".{chosen_collection}" if chosen_collection else ""),
                started=started,
                rows=rows,
                stats={"db": chosen, "collection": chosen_collection},
            )

        return await run_tool(
            runtime, tool="mongo_stats", name=target, environment=environment, target_type="mongo",
            params=params, handler=handler,
        )

    # ------------------------------------------------------------ Elasticsearch
    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def es_mapping(
        target: str, index: str, environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """查看索引字段 mapping 与分片设置。"""
        params = {"index": index}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_index(tgt, index)
            require(es_guard.check_http("GET", f"/{chosen}/_mapping"))
            require(es_guard.check_http("GET", f"/{chosen}/_settings"))
            connector = get_connector("elasticsearch")
            client = await runtime.catalog.client(tgt, connector)
            rows, stats = await connector.mapping(client, tgt, index=chosen)
            return finish(
                tgt,
                summary=f"GET /{chosen}/_mapping",
                started=started,
                rows=rows,
                stats={"index": chosen, **stats},
            )

        return await run_tool(
            runtime, tool="es_mapping", name=target, environment=environment, target_type="elasticsearch",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def es_search(
        target: str,
        index: str,
        query: str = "",
        from_: Annotated[int, Field(alias="from")] = 0,
        size: int = 0,
        sort: str = "",
        search_after: str = "",
        environment: EnvironmentParam = "",
    ) -> dict[str, Any]:
        """搜索索引（script、深分页与超限 size 会被拒绝）。"""
        params = {
            "index": index, "query": query or None, "from": from_,
            "size": size or None, "sort": sort or None,
            "search_after": search_after or None,
        }

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_index(tgt, index)
            body: dict[str, Any] = {}
            query_obj = _json_object(query, "query", required=False)
            body["query"] = query_obj or {"match_all": {}}
            cap = connectors_base.max_rows(tgt)
            if size < 0:
                raise errors.InvalidArgument("size 不能为负数")
            requested = size or cap
            if requested > cap:
                raise errors.GuardRejected(
                    f"size {requested} 超过目标上限 {cap}",
                    code=errors.DANGEROUS_OPERATION,
                )
            if from_ < 0:
                raise errors.InvalidArgument("from 不能为负数")
            if search_after:
                if from_:
                    raise errors.InvalidArgument("search_after 不能与 from 同时使用")
                if not sort:
                    raise errors.InvalidArgument("search_after 必须配合 sort 使用")
                try:
                    after_value = json.loads(search_after)
                except ValueError as exc:
                    raise errors.InvalidArgument(f"search_after 不是合法 JSON：{exc}") from exc
                if not isinstance(after_value, list):
                    raise errors.InvalidArgument("search_after 必须是 JSON 数组")
                body["search_after"] = after_value
                body["from"] = 0
            else:
                body["from"] = from_
            available = max(10_000 - from_, 1)
            body["size"] = min(requested + 1, available)
            if sort:
                try:
                    body["sort"] = json.loads(sort)
                except ValueError as exc:
                    raise errors.InvalidArgument(f"sort 不是合法 JSON：{exc}") from exc
            require(es_guard.check_http("POST", f"/{chosen}/_search", body))
            connector = get_connector("elasticsearch")
            client = await runtime.catalog.client(tgt, connector)
            fetched, stats = await connector.search(client, tgt, index=chosen, body=body)
            rows, truncation = trim_rows(fetched, requested)
            return finish(
                tgt,
                summary=f"POST /{chosen}/_search (from={from_}, size={requested})",
                started=started,
                rows=rows,
                stats={"index": chosen, **stats},
                truncation=truncation,
            )

        return await run_tool(
            runtime, tool="es_search", name=target, environment=environment, target_type="elasticsearch",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def es_health(
        target: str, environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """集群健康概览。"""
        params: dict[str, Any] = {}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            require(es_guard.check_http("GET", "/_cluster/health"))
            connector = get_connector("elasticsearch")
            client = await runtime.catalog.client(tgt, connector)
            stats = await connector.health(client, tgt)
            return finish(
                tgt, summary="GET /_cluster/health", started=started, rows=[], stats=stats
            )

        return await run_tool(
            runtime, tool="es_health", name=target, environment=environment, target_type="elasticsearch",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def es_index_stats(
        target: str, index: str, environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """索引文档数与存储统计。"""
        params = {"index": index}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_index(tgt, index)
            require(es_guard.check_http("GET", f"/{chosen}/_stats"))
            connector = get_connector("elasticsearch")
            client = await runtime.catalog.client(tgt, connector)
            rows = await connector.index_stats(client, tgt, index=chosen)
            return finish(
                tgt,
                summary=f"GET /{chosen}/_stats",
                started=started,
                rows=rows,
                stats={"index": chosen},
            )

        return await run_tool(
            runtime, tool="es_index_stats", name=target, environment=environment, target_type="elasticsearch",
            params=params, handler=handler,
        )

    # ------------------------------------------------------------------ Redis
    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def redis_get(
        target: str, key: str, environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """查看单个 key 的类型、TTL 与有限内容。"""
        params = {"key": key}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_key(tgt, key)
            connector = get_connector("redis")
            client = await runtime.catalog.client(tgt, connector)
            row = await connector.inspect(
                client,
                tgt,
                key=chosen,
                limit=connectors_base.max_rows(tgt),
                byte_limit=connectors_base.max_bytes(tgt),
            )
            return finish(
                tgt,
                summary=f"GET {chosen}",
                started=started,
                rows=[row],
                stats={"key": chosen, "type": row.get("type")},
            )

        return await run_tool(
            runtime, tool="redis_get", name=target, environment=environment, target_type="redis",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def redis_scan(
        target: str,
        pattern: str = "*",
        count: int = 10,
        cursor: int = 0,
        environment: EnvironmentParam = "",
    ) -> dict[str, Any]:
        """游标扫描 key（COUNT ≤ 200；pattern 受 key 前缀限制）。"""
        params = {"pattern": pattern, "count": count, "cursor": cursor}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            value = (pattern or "*").strip()
            prefix = str(tgt.options.get("key_prefix") or "")
            if prefix and not value.startswith(prefix):
                raise errors.ScopeDenied(f"pattern 必须以 {prefix} 开头")
            if count < 1 or count > 200:
                raise errors.GuardRejected(
                    "SCAN COUNT 必须在 1–200 之间", code=errors.DANGEROUS_OPERATION
                )
            if cursor < 0:
                raise errors.InvalidArgument("cursor 不能为负数")
            require(redis_guard.check_redis("SCAN", [cursor, "MATCH", value, "COUNT", count]))
            connector = get_connector("redis")
            client = await runtime.catalog.client(tgt, connector)
            keys, next_cursor = await connector.scan(
                client, tgt, pattern=value, count=count, cursor=cursor
            )
            return finish(
                tgt,
                summary=f"SCAN {value} COUNT {count}",
                started=started,
                rows=[{"key": item} for item in keys],
                stats={"cursor": next_cursor, "pattern": value, "count": count},
            )

        return await run_tool(
            runtime, tool="redis_scan", name=target, environment=environment, target_type="redis",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def redis_info(
        target: str, section: str = "", environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """读取 INFO（可指定 section）。"""
        params = {"section": section or None}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            require(redis_guard.check_redis("INFO", [section] if section else []))
            connector = get_connector("redis")
            client = await runtime.catalog.client(tgt, connector)
            stats = await connector.info(client, tgt, section=section or None)
            return finish(
                tgt,
                summary=f"INFO {section or 'all'}",
                started=started,
                rows=[],
                stats=stats,
            )

        return await run_tool(
            runtime, tool="redis_info", name=target, environment=environment, target_type="redis",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def redis_slowlog(
        target: str, count: int = 10, environment: EnvironmentParam = ""
    ) -> dict[str, Any]:
        """读取慢日志（SLOWLOG GET）。"""
        params = {"count": count}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            cap = min(max(count, 1), connectors_base.max_rows(tgt))
            require(redis_guard.check_redis("SLOWLOG", ["GET", cap]))
            connector = get_connector("redis")
            client = await runtime.catalog.client(tgt, connector)
            rows = await connector.slowlog(client, tgt, count=cap)
            prefix = str(tgt.options.get("key_prefix") or "")
            if prefix:
                rows = [row for row in rows if _slowlog_matches(row, prefix)]
            return finish(
                tgt,
                summary=f"SLOWLOG GET {cap}",
                started=started,
                rows=rows,
                stats={"count": cap, "key_prefix": prefix or None},
            )

        return await run_tool(
            runtime, tool="redis_slowlog", name=target, environment=environment, target_type="redis",
            params=params, handler=handler,
        )
