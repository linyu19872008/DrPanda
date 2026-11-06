# Changelog

[English](CHANGELOG.md) · [简体中文](CHANGELOG.zh-CN.md)

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-11-06

### Added

- Read-only MCP service for MySQL, MongoDB, Elasticsearch, Redis, GitLab, RabbitMQ, Kafka and CLS.
- Web console for target registration, connection tests, encrypted secrets, environments and MCP tokens.
- First-run setup wizard, login sessions, CSRF protection, login lockout and MCP bearer tokens.
- Audit log with outcome/failure details, filters and retention cleanup.
- System settings for target defaults, concurrency, audit maintenance, session/token limits and backup retention.
- Automatic loading of `./.env`, strict permission/format validation and environment-variable precedence.
- GitHub open-source documentation: bilingual README, contribution/security/conduct policies, issue/PR templates and CI.

### Security

- Absolute read-only guards plus dangerous/high-cost operation rules; target scope limits.
- Encrypted target secrets and hashed MCP tokens; no credentials in logs or audit.
- Configurable Cookie Secure policy and optional MCP host allowlist.

### Notes

- Kafka, CLS and GitLab tools are implemented and unit-tested but not end-to-end verified against real upstreams.
- Reverse-proxy HTTPS/TLS deployment still requires environment-specific validation.
