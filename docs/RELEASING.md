# Releasing & deployment (maintainer guide)

This is the maintainer runbook: versioning, release cadence, cutting a release, deploying and upgrading a server, migrations, rollback, and backups. The operator-facing self-host guide is [deployment.md](./deployment.md); this file is the "how we ship it" side.

## How shipping works (the 60-second model)

CI (`.github/workflows/ci.yml`) runs ruff + mypy + pytest on every push and PR; it does NOT build images (a full uv image build blows the CI time budget, by design). Images are built and published only when a version tag is pushed: `.github/workflows/release.yml` triggers on any `v*` tag and builds both images, tagging each with the version and `latest`:

- `ghcr.io/boffti/kortny` (the app image, runs app / worker / ambient / dashboard / sandbox-runner control plane via command override)
- `ghcr.io/boffti/kortny-sandbox-exec` (the throwaway code-execution image)

Operators run those images through `compose.prod.yaml`, pinned with `KORTNY_VERSION`. The `migrate` service applies Alembic to head on every boot. There is no separate deploy pipeline: a release is a git tag; a deploy is `pull` + `up -d` on the server.

## Versioning

Semantic versioning with a `v` prefix on the git tag. The image tag is the version with the `v` stripped (`v1.2.3` produces `ghcr.io/boffti/kortny:1.2.3` and `:latest`).

Pre-1.0 (we are at `0.x` today) the rules are relaxed:

- `0.MINOR.0` for features and notable changes (breaking changes are allowed pre-1.0; call them out in the release notes).
- `0.x.PATCH` for fixes and small, safe changes.

`v1.0.0` is the launch release. After 1.0, follow strict semver: MAJOR for breaking config/API/schema-removal changes, MINOR for backward-compatible features, PATCH for fixes.

`pyproject.toml` carries a nominal `version` that is NOT the source of truth for image tags (the git tag is). Keep it roughly in step if you like, but the tag is what ships.

## Release cadence

The working rhythm: build through the week with sanity checks and smoke tests, then a thorough manual test pass on the weekend before anything is tagged. Code that needs live verification is not tagged until it has been manually exercised. Tag a release when a meaningful, tested batch of work has landed on `main` and CI is green, not on a fixed clock.

Branching: work lands on `main` (one squashed commit per HIG; commits reference their HIG id). Every push runs CI. There are no long-lived release branches; a tag on `main` is the release.

## Pre-release checklist

Run before tagging. All must be true.

- [ ] `main` is green in CI (lint + mypy + tests).
- [ ] Local gate passes: `make check` (ruff check, ruff format --check, mypy, pytest).
- [ ] Any schema change has a new Alembic migration in `kortny/db/migrations/versions/` (never edit an applied one), and the migration was tested against a real DB.
- [ ] If the schema changed, `docs/schema.dbml` was regenerated (regen command is in that file's header).
- [ ] The weekend manual test pass is done for anything that needs live verification.
- [ ] `.env.example` covers any new required settings, and `compose.prod.yaml` defaults are sane.
- [ ] Release notes drafted (what changed, any breaking changes, any new required env or migration caveats).

## Cutting a release

```sh
# 1. Be on a clean, green main
git checkout main && git pull
make check                      # final local gate

# 2. Decide the version (semver; pre-1.0 rules above), then tag and push
git tag -a v0.2.0 -m "v0.2.0"   # annotated tag
git push origin v0.2.0          # this push triggers release.yml

# 3. Watch the build (~ up to 45 min budget; both images, GHA-cached)
gh run watch                    # or: gh run list --workflow=release.yml

# 4. Verify the images exist and are tagged
#    GHCR: ghcr.io/boffti/kortny:0.2.0 and :latest
#          ghcr.io/boffti/kortny-sandbox-exec:0.2.0 and :latest
docker pull ghcr.io/boffti/kortny:0.2.0

# 5. Publish a GitHub Release with the notes (this is our changelog)
gh release create v0.2.0 --title "v0.2.0" --notes "…"
```

### First release (one-time)

No tags exist yet, so `:latest` is not on GHCR until the first `v*` tag finishes building. The README one-line installer and `compose.prod.yaml` both default to `:latest`, so they only work after the first release publishes. Cut `v0.1.0` (or go straight to the launch `v1.0.0`) to populate `:latest`. Until then, anyone deploying must build locally or wait for the first tag.

## Deploying and upgrading a server

Pin a real version in production. Do not run `:latest` on a server you care about (you can't tell what you're running, and a re-pull silently moves you forward).

```sh
# On the server, in the repo dir, with a complete .env
export KORTNY_VERSION=0.2.0
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

`up -d` re-runs the one-shot `migrate` service first, which applies Alembic to head, then starts the long-running services against the new schema. First-time provisioning of a fresh box is the one-line installer (`scripts/install.sh`); upgrades are the two commands above with a bumped `KORTNY_VERSION`.

Upgrade order matters only when a migration is not backward compatible (see below). For ordinary releases, `pull` + `up -d` is the whole upgrade.

## Database migrations & safety

Alembic is the schema source of truth alongside the ORM models; `docs/schema.dbml` is a generated snapshot. Migrations live in `kortny/db/migrations/versions/` as `NNNN_slug.py` and run automatically via the `migrate` service on every `up -d`.

Rules:

- Always create migrations with Alembic (`make migrate` applies; author new ones, never hand-edit an applied migration).
- Prefer backward-compatible migrations: add columns/tables nullable-or-defaulted, backfill, then tighten in a later release. This lets the new schema run against briefly-still-old code and makes rollback survivable.
- Avoid destructive changes (drop column/table) in the same release that stops writing to them. Stop writing first (one release), drop later (a following release), so a rollback in between doesn't hit a missing column.
- After any schema change, regenerate `docs/schema.dbml` (command in its header) so the snapshot stays honest.

## Rollback

Code rollback is easy; schema rollback is the dangerous part. Plan migrations so you rarely need a schema rollback.

```sh
# Code-only rollback: re-pin the previous version and redeploy
export KORTNY_VERSION=0.1.0
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

This is safe ONLY if the newer release's migrations are backward compatible with the older code (the reason for the migration rules above). If a release contained a non-backward-compatible migration, a clean rollback means restoring the database from the pre-upgrade backup, not just re-pinning the image. Take a backup immediately before any upgrade that carries a risky migration.

Alembic `downgrade` exists (`make downgrade` goes to base) but per-step downgrades are not guaranteed safe for data, so treat backup-restore as the real rollback path for schema changes.

## Backups

A daily Postgres backup ships in `compose.prod.yaml` behind the `backup` profile (off by default). It dumps a gzipped `pg_dump` to a named volume and keeps the last 7.

```sh
docker compose -f compose.yaml -f compose.prod.yaml --profile backup up -d backup
```

Take an on-demand dump before any risky upgrade. The manual dump/restore commands and retention guidance are in [deployment.md](./deployment.md). Verify a restore works at least once; an untested backup is not a backup.

## Hotfixes

For an urgent production fix: land the fix on `main` (CI green, `make check`), tag a PATCH bump (`vX.Y.Z+1`), let `release.yml` publish, then `pull` + `up -d` on the server. Same path as any release, just scoped to the one fix.

## Changelog & tracking

GitHub Releases are the changelog: every tag gets a release with human-readable notes. There is no separate `CHANGELOG.md` (add one only if you want it duplicated in-repo). Work is tracked as Linear HIGs; commits and release notes reference HIG ids, so the trail from "what shipped in v0.2.0" back to the issue is intact.

## Cheat sheet

| Task | Command |
|---|---|
| Local gate | `make check` |
| New migration applied | `make migrate` |
| Cut a release | `git tag -a vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z` |
| Watch release build | `gh run watch` |
| Publish release notes | `gh release create vX.Y.Z --notes "…"` |
| Upgrade a server | `KORTNY_VERSION=X.Y.Z docker compose -f compose.yaml -f compose.prod.yaml pull && … up -d` |
| Roll back code | re-pin previous `KORTNY_VERSION`, pull, up -d |
| Regenerate schema snapshot | see header of `docs/schema.dbml` |
| Enable daily backups | `docker compose … --profile backup up -d backup` |
