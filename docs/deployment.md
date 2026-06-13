# Production deployment

This guide covers running Kortny in production from the published container
images, fronted by a reverse proxy, with the fail-fast secret guard armed.

The dev path (`docker compose up -d` against `compose.yaml`) builds nothing and
bind-mounts your source — great for hacking, wrong for production. Production
runs the **published GHCR images** with no source mount, restart policies,
resource limits, secure cookies, and a startup guard that refuses to boot with
placeholder secrets.

## One-line install (fastest)

On a fresh Linux server (Ubuntu/Debian/EC2/DigitalOcean/Hetzner):

```sh
curl -fsSL https://raw.githubusercontent.com/boffti/kortny/main/scripts/install.sh | bash
```

`scripts/install.sh` installs Docker if it's missing, pulls the GHCR images,
generates the secret-guard secrets (`ENCRYPTION_KEY`, `DASHBOARD_SESSION_SECRET`,
`DASHBOARD_PASSWORD`), and brings the stack up **with the sandbox**. It's
idempotent — re-run it to pull newer images or repair config. If you paste your
Slack/LLM/Composio keys when prompted it boots the full stack; otherwise it
starts Postgres + the dashboard so you can finish in the setup wizard. The rest
of this guide is the manual equivalent (pin a version, customize the overlay,
front it with a reverse proxy).

> **Why not a Railway/Render/Vercel one-click button?** The sandbox (code
> execution, document rendering, skill scripts) needs a Docker socket to spawn
> throwaway containers; those PaaS platforms don't expose one, so a one-click
> there would run with the sandbox disabled. Deploy to a real VM instead.

## Images

Two images are published to GHCR on every `v*` tag (see
`.github/workflows/release.yml`):

| Image | Built from | Role |
|---|---|---|
| `ghcr.io/boffti/kortny` | `docker/kortny.Dockerfile` | The app image. One multi-stage image for every Python service (app, worker, ambient, dashboard, sandbox-runner control plane, temporal worker). The service is chosen by overriding the container command. Runs as non-root uid `10001`. |
| `ghcr.io/boffti/kortny-sandbox-exec` | `docker/sandbox-exec.Dockerfile` | The sandbox **execution** image. Throwaway / session code containers boot from this; it carries the baked builder-skill deps (openpyxl, python-pptx, weasyprint, matplotlib, …) because those containers run with `--network none` and a read-only root filesystem and cannot `pip install` at runtime. |

Pick a tag with `KORTNY_VERSION` (defaults to `latest`):

```sh
export KORTNY_VERSION=v1.2.3
docker compose -f compose.yaml -f compose.prod.yaml pull
```

## Prerequisites

- Docker + Docker Compose v2.
- A reverse proxy terminating TLS in front of the dashboard (Caddy or nginx
  snippets below). The dashboard stays bound to `127.0.0.1:8080`.
- A complete-enough `.env` (see below). Slack / LLM / Composio keys can be
  absent on first boot — the dashboard's setup wizard collects them.

### Resource sizing

A small production host (e.g. 4 vCPU / 8 GB) is comfortable for a single team.
The prod overlay sets per-service memory limits as a guardrail:

| Service | Memory limit |
|---|---|
| postgres | 1 GB |
| worker | 2 GB (embeddings + LLM payloads) |
| app / ambient | 1 GB each |
| dashboard / sandbox-runner | 512 MB each |
| sandbox-docker-proxy | 128 MB |

On Docker Desktop (dev), give the VM **6–8 GB** — the worker pulls embedding
models into memory and the sandbox spins up sibling containers.

## Required environment

All vars are declared in `kortny/config/settings.py` (runtime) and
`kortny/dashboard/settings.py` (dashboard) — those files are authoritative.

The prod overlay arms a startup **secret guard** (`KORTNY_REQUIRE_SECURE_ENV=1`,
implemented in `docker/entrypoint.sh`). It refuses to start any service until
the security-critical vars are set and not at their shipped placeholders. It
deliberately does **not** require Slack / LLM / Composio keys, so the dashboard
setup wizard (HIG-209) still boots when those are absent.

| Var | Why it is guarded | Failing default |
|---|---|---|
| `ENCRYPTION_KEY` | Secrets at rest (MCP server secrets, provider keys) are Fernet-encrypted with a key derived from it. | empty |
| `DASHBOARD_SESSION_SECRET` | Signs dashboard session cookies; must be ≥ 16 chars. | empty / `change-me-dashboard-session-secret` / too short |
| `DASHBOARD_PASSWORD` | Bootstrap admin login. | empty / `change-me` |

Other production-relevant vars:

- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` — set a real password.
- `DASHBOARD_AUTH_MODE` (`bootstrap` / `slack` / `hybrid`) and the
  `DASHBOARD_SLACK_*` vars if you want Sign in with Slack.
- `KORTNY_PUBLIC_BASE_URL` + `KORTNY_PREVIEW_SIGNING_SECRET` for shareable
  sandbox preview links.

The prod overlay forces `DASHBOARD_SECURE_COOKIES=true` — keep TLS in front of
the dashboard or browsers will drop the session cookie.

## First boot

```sh
git clone https://github.com/boffti/kortny && cd kortny
cp .env.example .env          # fill in at least the three guarded secrets
export KORTNY_VERSION=v1.2.3

docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

`migrate` runs `alembic upgrade head` (from the app image, so migrations match
the deployed code) before app/worker/ambient start. If your `.env` is missing
Slack/LLM/Composio keys, the dashboard boots into setup-wizard mode at
`https://<your-host>/setup`; finish the wizard, paste the rendered block into
`.env`, and `up -d` again.

If a guarded secret is missing, the container exits immediately with a clear
multi-line refusal naming each offending var (exit code 78, `EX_CONFIG`).

## Reverse proxy

The dashboard listens on `127.0.0.1:8080`. Terminate TLS in front of it.

### Caddy

```caddyfile
kortny.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

### nginx

```nginx
server {
    listen 443 ssl;
    server_name kortny.example.com;

    ssl_certificate     /etc/ssl/kortny/fullchain.pem;
    ssl_certificate_key /etc/ssl/kortny/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Slack ingress uses **Socket Mode** (outbound WebSocket) — no inbound webhook is
exposed, so the proxy only needs to cover the dashboard.

## Backups

Postgres holds everything (tasks, memory, costs, schedules). The named volume
`postgres-data` persists across restarts; back it up logically with `pg_dump`.

Manual dump:

```sh
docker compose -f compose.yaml -f compose.prod.yaml exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > kortny-$(date +%F).sql.gz
```

Restore:

```sh
gunzip -c kortny-2026-06-12.sql.gz | docker compose -f compose.yaml -f compose.prod.yaml \
    exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

An optional daily backup service is included under the `backup` profile (dumps
to the `postgres-backups` volume, retains the most recent 7):

```sh
docker compose -f compose.yaml -f compose.prod.yaml --profile backup up -d backup
```

For real disaster recovery, copy those dumps off the host (object storage, etc.)
on your own schedule — the volume alone does not survive host loss.

## Upgrades

Images are immutable per tag; upgrading is a pull + recreate. `migrate` runs
automatically on `up` and applies any new migrations before the app/worker boot.

```sh
export KORTNY_VERSION=v1.3.0
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

Take a `pg_dump` before a major upgrade. Migrations are forward-only; never edit
applied ones.

## Sandbox container GC

The sandbox-runner spins up `kortny.sandbox=true`-labeled containers (ephemeral
one-shot runs and long-lived workbench sessions). A GC thread sweeps leaked ones
so a crashed runner or an un-closed session does not pile up containers:

- a startup sweep, then a periodic re-sweep every
  `KORTNY_SANDBOX_GC_INTERVAL_SECONDS` (default 600);
- terminal containers (exited/created/dead) older than
  `KORTNY_SANDBOX_GC_MAX_AGE_MINUTES` (default 60) are removed;
- a still-running but **orphaned** container is removed only when far older than
  `KORTNY_SANDBOX_GC_ORPHAN_RUNNING_MAX_AGE_HOURS` (default 24), and never if it
  belongs to a session the runner still tracks live.

Disable with `KORTNY_SANDBOX_GC_ENABLED=false`. The GC never touches a container
that is not `kortny.sandbox`-labeled.

