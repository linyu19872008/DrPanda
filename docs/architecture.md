# Architecture

DrPanda MCP is a single-process, read-only service that exposes a web console and an MCP endpoint over the same HTTP listener (default `127.0.0.1:8111`).

## Goals

- Models can query production systems only through targets registered by an administrator.
- Every operation is read-only; dangerous or high-cost operations are rejected before connecting.
- Credentials are stored encrypted and are never available to models.
- Every call is audited under the real administrator or MCP token.

## Components

| Component | Responsibility |
|---|---|
| Web console | Target/environment management, connection tests, settings, users, audit, profile and MCP tokens |
| MCP endpoint (`/mcp`) | Streamable HTTP transport authenticated with a bearer token |
| Tool layer | Argument validation, target resolution, guard decisions, result envelope and audit |
| Guards | Read-only whitelist and dangerous/high-cost rules for each upstream type |
| Connectors | Minimal clients for MySQL, MongoDB, Elasticsearch, Redis, GitLab, RabbitMQ, Kafka and CLS |
| Connector catalog | Per-target client cache, concurrency slots and connection tests |
| Config store | SQLAlchemy models plus Alembic migrations; SQLite by default, MySQL/PostgreSQL supported |
| Runtime | Engine, migrations, secret encryption, session key and settings loader |

## Request flow

1. A client sends `POST /mcp` with `Authorization: Bearer <token>`.
2. Authentication middleware validates the token hash, user state and optional token expiry.
3. The model calls a tool with `environment` and `target`; hosts, accounts and passwords are never accepted as tool arguments.
4. The tool resolves the target and checks environment/target state and secret availability.
5. The guard layer validates the SQL, command, pipeline or API request against the read-only rules.
6. A per-target (and optional global) concurrency slot is acquired.
7. The connector runs with timeout, row and byte limits.
8. The result envelope is returned and one audit row is written, including the failure code and a redacted error detail when available.

## Read-only guarantees

- Only a small allowlist of read operations is accepted; write/admin/DDL commands are rejected before connecting.
- Absolute dangerous rules reject unbounded scans, large aggregations, deep pagination, script execution and similar high-cost operations.
- MySQL sessions request read-only transactions and statement timeouts.
- Every error is mapped to a stable error code; the model receives `CODE: message` and never raw credentials.

## Configuration

- Startup configuration comes from environment variables; `./.env` is loaded automatically from the current directory (real environment variables win).
- Runtime policy lives in the config store and is editable at `/settings` (target defaults, concurrency, audit maintenance, auth/token limits, backup retention).
- The config-store URL chosen during the setup wizard is stored in `data/install.json`; `DR_PANDA_DATABASE_URL` is not used to select the actual store in the current version.

## Deployment assumptions

- Default listen is loopback. Binding to a non-loopback address is allowed after installation; use an HTTPS reverse proxy for remote access.
- The first installation must be completed on loopback.
- SQLite is the default store and migration backups are kept under `data/backup/` when a pending Alembic migration exists.
- The process is designed as a single instance; audit cleanup and connector caches are in-process.

See [Security](security.md), [UI design](ui-design.md) and [Verification](verification.md) for details.
