# Changelog

[English](CHANGELOG.md) · [简体中文](CHANGELOG.zh-CN.md)

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.1] - 2026-11-07

### Fixed

- One-click client installation could not run from the hardened systemd service: the service did not have `uv` on PATH, had no writable uv cache, and `ProtectSystem=strict` blocked `.venv` updates.
- The generated unit now copies `uv` to `/usr/local/bin`, sets `UV_CACHE_DIR` under `data/`, and allows writes to the existing `.venv`/`uv.lock` only.

## [1.2.0] - 2026-11-07

### Added

- New/edit target forms now offer the same one-click client installation as the target list, for every optional target client (`mysql`, `mongo`, `redis`, `kafka`, `cls`).
- Probe responses expose a structured `install_extra`; the form shows an install action, installs the fixed extra, and automatically retries the connection.
- New `POST /targets/install-client` endpoint for unsaved target forms; it accepts only a target type and derives the fixed extra server-side.
- Install failures are surfaced without exposing the raw `uv sync` command.

## [1.1.3] - 2026-11-07

### Fixed

- Login page language/theme switches were blocked by authentication when logged out, redirecting to `/login?next=/language`; after login the browser then issued `GET /language` and received 405.
- `/language` and `/theme` are now public cookie-only routes.
- Login `next` no longer accepts POST-only routes, and unauthenticated non-GET requests do not preserve their POST path as the post-login landing page.

## [1.1.2] - 2026-11-07

### Fixed

- MySQL migration 0007 failed at `batch.alter_column` because MySQL requires the existing column type for `CHANGE/MODIFY COLUMN`. The migration now passes `existing_type` and `existing_nullable`.
- Added a real MySQL/PostgreSQL first-install integration check that runs the full SetupApp flow, pages, schema checks and an idempotent re-migration.
- Added a CI job with MySQL 8.0 and PostgreSQL 16 service containers.

## [1.1.1] - 2026-11-07

### Fixed

- MySQL first-install migration failed because `key` is a reserved word in migration `0007_environments`. The migration now uses SQLAlchemy expressions, so identifiers are quoted per dialect.
- Added regression tests that compile the environment lookup/insert for the MySQL dialect.

## [1.1.0] - 2026-11-06

### Added

- Deployment helper `scripts/setup.sh` with `check`, `install`, `service`, `start`, `status` and `upgrade`.
- Source (`git + uv sync`) and PyPI (`uv tool install`) installation methods.
- systemd unit for a dedicated `drpanda` user, with sandboxing and health-checked startup.
- Automatic Python selection (system Python >=3.11 first; shared `/opt/uv-python` fallback), `--no-dev` production installs, and optional PyPI/python mirrors.
- Preflight and post-install checks for interpreter accessibility, service-user execution and systemd unit validity.

### Changed

- Repository renamed from `DrPanda` to `dr-panda-mcp` for consistency with the package and CLI.
- Documentation defaults to English under `docs/`; Chinese docs live under `docs/zh-CN/`.

### Fixed

- systemd unit path directives no longer use quotes.
- Service startup failures are reported instead of being treated as success.

## [1.0.0] - 2026-11-06

### Added

- Read-only MCP service for MySQL, MongoDB, Elasticsearch, Redis, GitLab, RabbitMQ, Kafka and CLS.
- Web console for target registration, connection tests, encrypted secrets, environments and MCP tokens.
- First-run setup wizard, login sessions, CSRF protection, login lockout and MCP bearer tokens.
- Audit log with outcome/failure details, filters and retention cleanup.
- System settings for target defaults, concurrency, audit maintenance, session/token limits and backup retention.
- Automatic loading of `./.env`, strict permission/format validation and environment-variable precedence.
- English is the default language for the web UI, MCP, CLI and documentation; Chinese docs live under `docs/zh-CN/`.
- GitHub open-source documentation: bilingual README, contribution/security/conduct policies, issue/PR templates and CI.

### Security

- Absolute read-only guards plus dangerous/high-cost operation rules; target scope limits.
- Encrypted target secrets and hashed MCP tokens; no credentials in logs or audit.
- Configurable Cookie Secure policy and optional MCP host allowlist.

### Notes

- Kafka, CLS and GitLab tools are implemented and unit-tested but not end-to-end verified against real upstreams.
- Reverse-proxy HTTPS/TLS deployment still requires environment-specific validation.
