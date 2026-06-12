# Changelog Format Reference

## Keep a Changelog format (default)

Based on https://keepachangelog.com/en/1.0.0/

```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.2.0] — 2026-06-12

### ⚠ Breaking
- Removed the `legacy_export` endpoint. Migrate to `/v2/export`. See migration guide: [link]

### Added
- PDF export now supports custom page sizes (A4 and Letter).
- New webhook event: `user.deactivated`.

### Changed
- Dashboard loading time reduced by 40% through query optimization.
- Notification emails now include an unsubscribe link.

### Deprecated
- `GET /api/v1/report` is deprecated. Use `/api/v2/report` instead. Removal in v2.0.

### Fixed
- Exports no longer fail when a row contains an empty date field.
- Fixed incorrect total displayed on the billing page for annual plans.

### Security
- Updated dependency X to address CVE-YYYY-NNNNN. See [advisory link].

## [1.1.0] — 2026-05-01
...
```

## Commit message → changelog entry mapping

| Commit prefix | Changelog category |
|---|---|
| `feat:` / `feature:` | Added |
| `improve:` / `perf:` / `refactor:` (with user impact) | Changed |
| `deprecate:` | Deprecated |
| `remove:` | Removed |
| `fix:` / `bugfix:` | Fixed |
| `security:` | Security |
| `chore:` / `ci:` / `test:` / `docs:` | OMIT (unless internal changelog) |
| `BREAKING CHANGE:` | ⚠ Breaking |

## Noise to strip
- Merge commits: `Merge branch 'main' into feature/foo`
- Version bumps: `chore: bump version to 1.2.0`
- Pure refactors with no user-visible change
- Typo fixes in internal docs
- CI configuration changes
