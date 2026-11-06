"""MySQL 只读闸门（planning 6.3 / 6.6）。

用 sqlglot 以 ``mysql`` 方言解析语法树；只认 AST，不做字符串前缀匹配。
允许单条 SELECT / SHOW / DESCRIBE / EXPLAIN（内层同样受限）；
危险与高开销操作返回 ``DANGEROUS_OPERATION``。
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from dr_panda_mcp.guards import forbidden
from dr_panda_mcp.guards.protocol import (
    Decision,
    allow,
    dangerous,
    guard_rejected,
)

DIALECT = "mysql"


def check_sql(sql: str) -> Decision:
    """检查一条只读 SQL；返回放行（含规范化信息）或拒绝。"""
    if not isinstance(sql, str) or not sql.strip():
        return guard_rejected("mysql.empty_sql", "SQL must not be empty")
    # MySQL 会执行 /*! ... */ 版本注释中的 SQL；sqlglot 会把它当普通注释丢掉，
    # 因此必须在解析前显式拒绝，否则可绕过系统库与危险函数检查。
    if "/*!" in sql:
        return dangerous(
            "mysql.executable_comment",
            "MySQL executable version comments (/*! ... */) are not allowed",
        )

    try:
        statements = [stmt for stmt in sqlglot.parse(sql, dialect=DIALECT) if stmt is not None]
    except ParseError as exc:
        return guard_rejected("mysql.parse_error", f"SQL cannot be parsed: {exc}")

    if not statements:
        return guard_rejected("mysql.empty_sql", "SQL must not be empty")
    if len(statements) != 1:
        return guard_rejected(
            "mysql.multi_statement",
            "only a single statement is allowed; multiple or semicolon-separated "
            "statements were detected",
        )

    statement = statements[0]
    if isinstance(statement, exp.Select):
        return _check_select(statement, sql)
    if isinstance(statement, exp.Show):
        return _check_show(statement)
    if isinstance(statement, exp.Describe):
        return _check_describe(statement, sql)
    return guard_rejected(
        "mysql.statement_not_allowed",
        f"only SELECT / SHOW / DESCRIBE / EXPLAIN are allowed, got "
        f"{type(statement).__name__}",
    )


def _check_select(statement: exp.Expression, sql: str) -> Decision:
    if list(statement.find_all(exp.Lock)):
        return dangerous(
            "mysql.locking_read",
            "locking reads such as FOR UPDATE / LOCK IN SHARE MODE are not allowed",
        )
    if list(statement.find_all(exp.Into)):
        return dangerous("mysql.into_clause", "SELECT ... INTO variables or files is not allowed")
    for table in statement.find_all(exp.Table):
        if (table.db or "").lower() in forbidden.MYSQL_SYSTEM_SCHEMAS:
            return dangerous(
                "mysql.system_schema", f"reading system schema {table.db} is not allowed"
            )
    for function in statement.find_all(exp.Anonymous):
        if function.name.upper() in forbidden.MYSQL_DANGEROUS_FUNCTIONS:
            return dangerous(
                "mysql.expensive_function", f"calling {function.name.upper()} is not allowed"
            )

    has_where = statement.args.get("where") is not None
    if not has_where:
        if (
            statement.args.get("order")
            or statement.args.get("group")
            or statement.args.get("distinct")
        ):
            return dangerous(
                "mysql.full_scan_sort",
                "sort/group/dedup without WHERE scans the whole table",
            )
        if list(statement.find_all(exp.AggFunc)):
            return dangerous(
                "mysql.full_scan_aggregate", "aggregation without WHERE scans the whole table"
            )

    return allow({"kind": "select", "sql": sql})


def _check_show(statement: exp.Show) -> Decision:
    command = str(statement.this or "").upper()
    if command not in forbidden.MYSQL_SHOW_COMMANDS:
        return guard_rejected(
            "mysql.show_not_allowed", f"SHOW command not allowed: {command or '(empty)'}"
        )
    return allow({"kind": "show", "command": command})


def _check_describe(statement: exp.Describe, sql: str) -> Decision:
    style = str(statement.args.get("style") or "").upper()
    if style == "ANALYZE":
        return dangerous(
            "mysql.explain_analyze",
            "EXPLAIN ANALYZE actually executes the statement and has "
            "unbounded cost",
        )
    inner = statement.this
    if isinstance(inner, exp.Select):
        return _check_select(inner, sql)
    if isinstance(inner, exp.Table):
        if (inner.db or "").lower() in forbidden.MYSQL_SYSTEM_SCHEMAS:
            return dangerous("mysql.system_schema", f"reading system schema {inner.db} is not allowed")
        return allow({"kind": "describe", "table": inner.name, "db": inner.db})
    return guard_rejected(
        "mysql.explain_target",
        "EXPLAIN / DESCRIBE target must be a SELECT or a table",
    )
