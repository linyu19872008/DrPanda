"""跨组件的只读白名单与危险清单常量（planning 6.3 / 6.6）。

这些是安全边界，写死在代码里，不从系统配置读取，也没有开关可以放开。
"""

from __future__ import annotations

from datetime import timedelta

# ---------------------------------------------------------------------------
# MySQL（命令级白名单在 guards/mysql.py 用 sqlglot AST 判定）
# ---------------------------------------------------------------------------
MYSQL_ALLOWED_STATEMENTS = frozenset({"select", "show", "describe", "explain"})
MYSQL_SYSTEM_SCHEMAS = frozenset(
    {"information_schema", "performance_schema", "mysql", "sys"}
)
MYSQL_SHOW_COMMANDS = frozenset(
    {
        "TABLES",
        "COLUMNS",
        "FULL COLUMNS",
        "INDEX",
        "KEYS",
        "CREATE TABLE",
        "STATUS",
        "VARIABLES",
        "PROCESSLIST",
        "DATABASES",
        "TABLE STATUS",
    }
)
MYSQL_DANGEROUS_FUNCTIONS = frozenset(
    {"SLEEP", "BENCHMARK", "GET_LOCK", "RELEASE_LOCK", "MASTER_POS_WAIT", "LOAD_FILE"}
)

# ---------------------------------------------------------------------------
# Mongo
# ---------------------------------------------------------------------------
MONGO_READ_COMMANDS = frozenset(
    {
        "find",
        "aggregate",
        "count",
        "distinct",
        "collStats",
        "dbStats",
        "listCollections",
        "listIndexes",
        "ping",
        "serverStatus",
        "currentOp",
    }
)
MONGO_PIPELINE_STAGES = frozenset(
    {"$match", "$project", "$group", "$sort", "$limit", "$lookup"}
)
MONGO_DANGEROUS_STAGES = frozenset({"$out", "$merge"})
MONGO_JS_OPERATORS = frozenset({"$where", "$function", "$accumulator"})
MONGO_MATCH_REQUIRED_STAGES = frozenset({"$group", "$lookup"})

# ---------------------------------------------------------------------------
# Elasticsearch
# ---------------------------------------------------------------------------
ES_ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST"})
ES_POST_PATH_SUFFIXES = ("_search", "_count")
ES_DANGEROUS_BODY_KEYS = frozenset(
    {"script", "script_fields", "scripted_metric", "runtime_mappings"}
)
ES_MAX_WINDOW = 10_000
ES_MAX_TERMS_SIZE = 100
ES_FORBIDDEN_PATH_PARTS = frozenset({"_all", "*"})

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
REDIS_READ_COMMANDS = frozenset(
    {
        "PING",
        "GET",
        "MGET",
        "STRLEN",
        "EXISTS",
        "TYPE",
        "TTL",
        "PTTL",
        "SCAN",
        "HGET",
        "HMGET",
        "HLEN",
        "HSCAN",
        "LLEN",
        "LRANGE",
        "SCARD",
        "SMEMBERS",
        "ZCARD",
        "ZRANGE",
        "INFO",
        "SLOWLOG",
        "DBSIZE",
        "MEMORY",
    }
)
REDIS_MAX_SCAN_COUNT = 200
REDIS_UNBOUNDED_RANGE_COMMANDS = frozenset({"LRANGE", "ZRANGE"})
REDIS_NEEDS_SIZE_PROBE = frozenset({"SMEMBERS"})

# ---------------------------------------------------------------------------
# GitLab / RabbitMQ：只发 GET
# ---------------------------------------------------------------------------
GITLAB_ALLOWED_METHODS = frozenset({"GET"})
RABBIT_ALLOWED_METHODS = frozenset({"GET"})
RABBIT_ALLOWED_PATH_PREFIX = "/api/"

# ---------------------------------------------------------------------------
# Kafka：描述类 + 有限拉取
# ---------------------------------------------------------------------------
KAFKA_READ_ACTIONS = frozenset(
    {
        "metadata",
        "describe_cluster",
        "describe_topics",
        "list_offsets",
        "list_consumer_groups",
        "describe_consumer_groups",
        "fetch",
    }
)
KAFKA_DANGEROUS_ACTIONS = frozenset(
    {
        "create_topics",
        "delete_topics",
        "delete_records",
        "alter_configs",
        "create_partitions",
        "join_group",
        "leave_group",
        "commit_offsets",
        "offset_commit",
        "produce",
        "init_producer_id",
    }
)

# ---------------------------------------------------------------------------
# CLS
# ---------------------------------------------------------------------------
CLS_READ_ACTIONS = frozenset(
    {"search_log", "describe_log_context", "describe_topics", "describe_logsets"}
)
CLS_DANGEROUS_ACTIONS = frozenset(
    {
        "upload_log",
        "delete_topic",
        "modify_topic",
        "create_export_task",
        "delete_export_task",
        "create_topic",
        "modify_logset",
        "delete_logset",
    }
)
CLS_MAX_WINDOW = timedelta(hours=24)
