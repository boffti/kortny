# Provenance

**Base SKILL.md**: Kortny-authored (Agent A, HIG-239, 2026-06-12) — original prose, Slack-first adaptations. Retained as primary body.
**References vendored from**: https://github.com/anthropics/skills, commit `57546260929473d4e0d1c1bb75297be2fdfa1949`, 2026-06-12.
**Vendored by**: Agent F (HIG-239 corrective pass)

## License verification

Directory `skills/frontend-design/LICENSE.txt` in upstream repo is Apache-2.0 (verified per-dir).

## What was vendored

| File | Upstream source | Adaptations |
|---|---|---|
| `references/aesthetics.md` | `skills/frontend-design/SKILL.md` (upstream's full opinionated aesthetic guide) | Structured into headed sections; generic "Claude Code" references stripped; Slack-file-delivery section added; CSS specificity warning retained; design examples retained; writing-in-design section retained in full |

## What was NOT taken from upstream

- `SKILL.md` body — Kortny-authored original (retained from Agent A)
- `references/design-principles.md` — Kortny-authored original (retained from Agent A); the existing file covers technical principles; `aesthetics.md` covers the higher-level design philosophy layer

## What the upstream adds beyond Agent A's version

The upstream `frontend-design/SKILL.md` is substantially richer than the Kortny clean-room rewrite in one key dimension: it includes a detailed process for avoiding default/templated AI-generated aesthetic choices — a two-pass brainstorm/critique/build method, a taxonomy of common AI design defaults to avoid, copy/writing philosophy, and a restraint/self-critique framework. These are surfaced in `references/aesthetics.md`.

## Apache-2.0 notice

The vendored `references/aesthetics.md` is derived from upstream content licensed under the Apache License, Version 2.0. A copy of that license is in `LICENSE.txt` in this directory.
