# Deployment

`scripts/setup.sh` is the supported deployment helper for a new machine. It supports both installation methods:

- **source**: `git clone` + `uv sync` (recommended for development / the console's client-install feature)
- **pypi**: `uv tool install dr-panda-mcp==<version>` (recommended for a runtime-only host)

The first installation must be completed on loopback (`127.0.0.1` / `localhost`), then remote access can be enabled.

## Commands

```bash
# Read-only checks; changes nothing
./scripts/setup.sh check

# Source installation (default; current checkout if run inside the repo)
./scripts/setup.sh install --method source --extras mysql,redis

# PyPI installation into a dedicated directory
sudo ./scripts/setup.sh install --method pypi --version 1.0.0 --dir /opt/dr-panda-mcp

# systemd service (Linux, root); dedicated user drpanda by default
sudo ./scripts/setup.sh service --dir /opt/dr-panda-mcp

# Start / health check; foreground if no systemd service is installed
./scripts/setup.sh start --dir /opt/dr-panda-mcp

# Status
./scripts/setup.sh status --dir /opt/dr-panda-mcp

# Upgrade source or PyPI installation, then restart the service
sudo ./scripts/setup.sh upgrade --dir /opt/dr-panda-mcp --version 1.0.1
```

## What `check` verifies

- OS/architecture, `curl`, `git`, `uv`;
- systemd availability (Linux);
- `.env` existence and mode (must not be group/other-readable);
- `data/` and key/install files;
- listen address/port and whether the port is in use;
- first-install rule: non-loopback listen is rejected until `data/install.json` exists;
- installed binary for the recorded method.

Use it before and after installation; it is read-only.

## First installation

1. Install with the default loopback address.
2. Start the service or run foreground.
3. Open `http://127.0.0.1:8111/` in a browser on the same machine, or use an SSH tunnel:

```bash
ssh -L 8111:127.0.0.1:8111 user@server
# then open http://127.0.0.1:8111/ locally
```

4. Complete the setup wizard and save the MCP token plus the `data/` key files.
5. Only then edit `.env` (for example `DR_PANDA_HOST="0.0.0.0"`) and restart.

## systemd

`service` creates a `drpanda` system user when needed, fixes ownership, and writes `/etc/systemd/system/dr-panda-mcp.service`.

The unit runs with:

- `ProtectSystem=strict`, `ReadWritePaths=<dir>/data`
- `ProtectHome=true` unless the app directory is under `/home`
- `NoNewPrivileges=true`
- automatic restart on failure

Inspect logs with:

```bash
journalctl -u dr-panda-mcp -f
```

## Upgrade and rollback

- Always back up `data/` together with `secret.key`, `install.json`, `install.key` and `session.key`.
- The app runs Alembic migrations on startup; SQLite backups are automatic only when a migration is pending.
- Source: `git pull --ff-only` + `uv sync`; roll back with the previous tag/commit.
- PyPI: install the previous version explicitly; database downgrade is not automatic.

## Options

| Option | Meaning |
|---|---|
| `--dir PATH` | Application directory |
| `--method source\|pypi` | Install method |
| `--version VER` | PyPI version |
| `--extras LIST` | `mysql,postgres,mongo,redis,kafka,cls` or `all` |
| `--user USER` | systemd service user (default `drpanda`) |
| `--service-name NAME` | systemd unit name |
| `--repo URL` | Git repository URL |
| `--yes` | Allow installing uv without prompting |
| `--no-start` | Install the unit but do not start it |

## Docker

Docker is not covered by this helper yet; evaluate it separately if needed.
