# Security model

DrPanda MCP is designed for production troubleshooting where credentials must never reach a model. Security is enforced in layers.

## Boundaries

1. **Connection boundary**: only targets registered in the web console can be reached. Tool calls use a target name, not a host, DSN, account or password.
2. **Operation boundary**: only a read-only whitelist is executed; admin commands, writes, DDL and high-cost operations are rejected before connecting.
3. **Identity boundary**: the web console and MCP use separate authentication mechanisms; every call is audited under a real actor.

## Read-only guards

- MySQL: single read-only statements; writes, management commands, system schemas, `EXPLAIN ANALYZE`, and unsafe full scans are rejected.
- MongoDB: read commands only; JavaScript execution, system collections, and unsafe aggregation stages are rejected.
- Elasticsearch: read/search APIs only; scripts, deep pagination and `track_total_hits` are rejected.
- Redis: bounded reads only; unbounded scans and probing limits are enforced.
- GitLab, RabbitMQ and Kafka: project/topic/queue scope checks before access.
- CLS: topic and time-window checks.

## Authentication

- Web: administrator password, HMAC-signed session cookie, CSRF double-submit protection.
- MCP: independent bearer tokens stored as hashes; the full value is shown once at creation.
- Token options: per-user token limit and optional token lifetime.
- Login protection: configurable failed-attempt limit and lockout window per source IP.
- Session lifetime is configurable; cookies can be forced `Secure`, `auto` (request scheme) or `never`.

## Secrets

- Target secrets are encrypted with a local key (`DR_PANDA_SECRET_KEY` or `data/secret.key`).
- Secrets, connection strings and passwords are redacted from logs, audit and error messages.
- Back up the config store together with `secret.key`, `install.json`, `install.key` and `session.key`; losing `secret.key` makes stored target secrets unrecoverable.

## Remote access

- Default listen is `127.0.0.1`. Changing `DR_PANDA_HOST` to `0.0.0.0` or a specific interface exposes the service.
- Use an HTTPS reverse proxy; do not expose the console directly to the public internet.
- `DR_PANDA_PUBLIC_URL` is display-only and does not affect security policy.
- Set `DR_PANDA_TRUSTED_HOSTS` to add an explicit `/mcp` Host allowlist.
- The first installation must be completed on loopback to prevent remote administrator takeover.

## Reporting vulnerabilities

Do not open a public issue. Follow [SECURITY.md](../SECURITY.md).
