# Verification and known boundaries

DrPanda MCP values honest verification. This page summarizes what is tested and what still needs environment-specific validation.

## CI and local checks

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run pytest -q
uv run python scripts/smoke.py
uv run python scripts/check_docs_links.py
```

GitHub Actions runs pytest and ruff on Python 3.11/3.12, builds the package, and checks documentation links. Test counts are intentionally not hard-coded here; use the CI badge or a local run.

## Test layers

- Unit tests for guards, connectors, masking, config parsing and crypto.
- Store/repository contract tests for SQLite and settings history.
- Web tests for server-rendered pages, auth, CSRF, async JSON fallbacks and analyst read-only access.
- Tool tests with fake connectors for scope, guard, truncation and audit behavior.
- Migration tests for fresh databases and upgrades with existing data.
- Real upstream integration for MySQL, MongoDB, Elasticsearch, Redis and RabbitMQ via Docker.

## Verified

- SQLite / MySQL / PostgreSQL config-store setup;
- multiple MCP tokens (create/copy/delete/paginate), token limits and expiry;
- login, sessions, CSRF, logout and password change;
- target lifecycle, connection-test save gate and encrypted secrets;
- system settings, grouped editing, reset and history;
- light/dark themes, English/Chinese, 1440/390 layouts;
- read-only guards, dangerous-operation rejection, timeout/row/byte limits;
- MySQL/Mongo/ES/Redis/RabbitMQ with real Docker upstreams.

## Not verified / boundaries

- Kafka end-to-end against a real upstream (image unavailable);
- CLS and GitLab end-to-end with real credentials;
- HTTPS/TLS behind a real reverse proxy;
- multi-user RBAC, OAuth/OIDC and MFA;
- password recovery page (only a local CLI reset exists);
- automatic recovery if `install.json`, `install.key` or `secret.key` are lost.

Unverified capabilities are never treated as available because other components pass.


## Language policy

- The web console defaults to English; `zh-Hans` is available through the language selector.
- The English web catalog must be complete; a missing English translation fails loudly instead of falling back to Chinese.
- MCP instructions, prompts, tool descriptions, parameter descriptions and tool errors are English-only.
- CLI, startup, configuration and log messages are English-only.
- Documentation defaults to English under `docs/`; Chinese documentation lives under `docs/zh-CN/`.
