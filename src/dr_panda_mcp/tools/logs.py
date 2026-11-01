"""日志到代码：CLS 与 GitLab 五个只读工具（planning 8.4）。"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base as connectors_base
from dr_panda_mcp.connectors import get_connector
from dr_panda_mcp.guards import cls as cls_guard
from dr_panda_mcp.guards import gitlab as gitlab_guard
from dr_panda_mcp.guards.protocol import require
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.protocol import Target
from dr_panda_mcp.tools.base import (
    TOOL_ANNOTATIONS,
    allowed_projects,
    clamp_limit,
    ensure_project,
    ensure_topic,
    finish,
    run_tool,
)


def register_logs_tools(server: FastMCP, runtime: Runtime) -> None:
    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def cls_search(
        target: str,
        query: str,
        topic: str,
        from_: Annotated[str, Field(alias="from")],
        to: Annotated[str, Field(alias="to")],
        limit: int = 0,
    ) -> dict[str, Any]:
        """按条件检索 CLS 日志；必须带时间窗，单次不超过 24 小时。"""
        params = {
            "query": query,
            "topic": topic,
            "from": from_,
            "to": to,
            "limit": limit or None,
        }

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            if not query.strip():
                raise errors.InvalidArgument("query 不能为空")
            window = require(cls_guard.check_cls("search_log", {"from": from_, "to": to}))
            chosen_topic = ensure_topic(tgt, topic)
            cap = clamp_limit(limit or None, tgt, connectors_base.max_rows(tgt))
            connector = get_connector("cls")
            client = await runtime.catalog.client(tgt, connector)
            rows = await connector.search_log(
                client,
                tgt,
                topic=chosen_topic,
                query=query,
                start=window["from"],
                end=window["to"],
                limit=cap,
            )
            return finish(
                tgt,
                summary=f"SearchLog topic={chosen_topic} query={query[:80]}",
                started=started,
                rows=rows,
                stats={"topic": chosen_topic, "query": query},
                time_range={
                    "from": window["from"].isoformat(),
                    "to": window["to"].isoformat(),
                },
            )

        return await run_tool(
            runtime,
            tool="cls_search",
            name=target,
            target_type="cls",
            params=params,
            handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def cls_context(
        target: str,
        topic: str,
        log_id: str,
        before: int = 10,
        after: int = 10,
    ) -> dict[str, Any]:
        """读取一条日志前后的上下文（按 PkgId 定位）。"""
        params = {"topic": topic, "log_id": log_id, "before": before, "after": after}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            require(cls_guard.check_cls("describe_log_context", {}))
            chosen_topic = ensure_topic(tgt, topic)
            if not log_id.strip():
                raise errors.InvalidArgument("log_id 不能为空")
            if not 0 <= before <= 20 or not 0 <= after <= 20:
                raise errors.InvalidArgument("before / after 必须在 0–20 之间")
            connector = get_connector("cls")
            client = await runtime.catalog.client(tgt, connector)
            rows = await connector.describe_context(
                client, tgt, topic=chosen_topic, log_id=log_id, before=before, after=after
            )
            return finish(
                tgt,
                summary=f"DescribeLogContext topic={chosen_topic} pkg={log_id}",
                started=started,
                rows=rows,
                stats={"topic": chosen_topic, "before": before, "after": after},
            )

        return await run_tool(
            runtime,
            tool="cls_context",
            name=target,
            target_type="cls",
            params=params,
            handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def gitlab_search_code(
        target: str,
        query: str,
        project: str = "",
        ref: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """在 GitLab 项目里搜索代码；project 省略时只在授权项目内搜索。"""
        params = {"query": query, "project": project or None, "ref": ref or None, "limit": limit}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            if not query.strip():
                raise errors.InvalidArgument("query 不能为空")
            require(gitlab_guard.check_gitlab("GET", "/api/v4/projects/search"))
            projects = (
                [ensure_project(tgt, project)] if project else allowed_projects(tgt)
            )
            cap = clamp_limit(limit, tgt, 20)
            connector = get_connector("gitlab")
            client = await runtime.catalog.client(tgt, connector)
            rows: list[dict[str, Any]] = []
            for name in projects:
                if len(rows) >= cap:
                    break
                items = await connector.search_code(
                    client,
                    tgt,
                    project=name,
                    query=query,
                    ref=ref or None,
                    limit=min(cap - len(rows), 100),
                )
                for item in items:
                    rows.append(
                        {
                            "project": name,
                            "path": item.get("path") or item.get("filename"),
                            "line": item.get("startline"),
                            "snippet": (item.get("data") or "").strip()[:500],
                        }
                    )
            # 跨项目搜索时保持结果总量受上限约束
            rows = rows[:cap]
            return finish(
                tgt,
                summary=f"GitLab search blobs query={query[:80]} projects={len(projects)}",
                started=started,
                rows=rows,
                stats={"projects": projects, "query": query},
            )

        return await run_tool(
            runtime,
            tool="gitlab_search_code",
            name=target,
            target_type="gitlab",
            params=params,
            handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def gitlab_get_file(
        target: str, project: str, path: str, ref: str = ""
    ) -> dict[str, Any]:
        """读取 GitLab 项目里的一个文件（按字节上限截断）。"""
        params = {"project": project, "path": path, "ref": ref or None}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen_project = ensure_project(tgt, project)
            require(gitlab_guard.check_gitlab("GET", "/api/v4/projects/repository/files"))
            if not path.strip():
                raise errors.InvalidArgument("path 不能为空")
            connector = get_connector("gitlab")
            client = await runtime.catalog.client(tgt, connector)
            content = await connector.get_file(
                client, tgt, project=chosen_project, path=path, ref=ref or None
            )
            byte_limit = connectors_base.max_bytes(tgt)
            truncated = len(content.encode("utf-8")) > byte_limit
            if truncated:
                content = content.encode("utf-8")[:byte_limit].decode("utf-8", "ignore")
            return finish(
                tgt,
                summary=f"GitLab file {chosen_project}/{path}",
                started=started,
                rows=[{"path": path, "ref": ref or None, "content": content}],
                stats={"path": path, "ref": ref or None, "bytes": len(content.encode())},
                truncation=connectors_base.Truncation("bytes", byte_limit)
                if truncated
                else None,
            )

        return await run_tool(
            runtime,
            tool="gitlab_get_file",
            name=target,
            target_type="gitlab",
            params=params,
            handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def gitlab_blame(
        target: str,
        project: str,
        path: str,
        ref: str = "",
        line_from: int = 0,
        line_to: int = 0,
    ) -> dict[str, Any]:
        """查看文件最近的改动（可按行号范围）。"""
        params = {
            "project": project,
            "path": path,
            "ref": ref or None,
            "line_from": line_from or None,
            "line_to": line_to or None,
        }

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen_project = ensure_project(tgt, project)
            require(gitlab_guard.check_gitlab("GET", "/api/v4/projects/repository/blame"))
            if not path.strip():
                raise errors.InvalidArgument("path 不能为空")
            if line_from < 0 or line_to < 0 or (line_to and line_from and line_to < line_from):
                raise errors.InvalidArgument("行号范围不合法")
            connector = get_connector("gitlab")
            client = await runtime.catalog.client(tgt, connector)
            payload = await connector.blame(
                client,
                tgt,
                project=chosen_project,
                path=path,
                ref=ref or None,
                line_from=line_from or None,
                line_to=line_to or None,
            )
            rows: list[dict[str, Any]] = []
            line_number = line_from or 1
            for group in payload:
                commit = group.get("commit") or {}
                for text in group.get("lines") or []:
                    rows.append(
                        {
                            "line": line_number,
                            "commit": (commit.get("short_id") or commit.get("id") or "")[:10],
                            "author": commit.get("author_name"),
                            "date": commit.get("committed_date")
                            or commit.get("authored_date"),
                            "content": str(text)[:500],
                        }
                    )
                    line_number += 1
            return finish(
                tgt,
                summary=f"GitLab blame {chosen_project}/{path}",
                started=started,
                rows=rows,
                stats={"path": path, "ref": ref or None},
            )

        return await run_tool(
            runtime,
            tool="gitlab_blame",
            name=target,
            target_type="gitlab",
            params=params,
            handler=handler,
        )
