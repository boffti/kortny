# Provenance

**Base SKILL.md**: Kortny-authored (Agent A, HIG-239, 2026-06-12) — original prose, Slack-first adaptations.
**References vendored from**: https://github.com/anthropics/skills, commit `57546260929473d4e0d1c1bb75297be2fdfa1949`, 2026-06-12.
**Vendored by**: Agent F (HIG-239 corrective pass)

## License verification

Directory `skills/internal-comms/LICENSE.txt` in upstream repo is Apache-2.0 (verified per-dir). The `examples/` subdirectory files are covered by that same LICENSE.txt.

## What was vendored

| File | Upstream path | Adaptations |
|---|---|---|
| `references/3p-updates.md` | `skills/internal-comms/examples/3p-updates.md` | Genericized Anthropic-specific references; Slack delivery framing; scheduler-pairing note; table added for scope calibration |
| `references/company-newsletter.md` | `skills/internal-comms/examples/company-newsletter.md` | Slack-first delivery (canvas option added); generic channel/tool references; section headers genericized |
| `references/faq-answers.md` | `skills/internal-comms/examples/faq-answers.md` | Slack post and canvas delivery options; source-link guidance added; scope framing genericized |
| `references/general-comms.md` | `skills/internal-comms/examples/general-comms.md` | Expanded from thin upstream; tone-calibration table; Slack delivery framing; checklist added |

## What was NOT taken from upstream

- `SKILL.md` body — Kortny-authored original (retained from Agent A)
- No upstream content from `doc-coauthoring/` (license ambiguous, per plan)

## Slack-first adaptations (all references)

- Output targets are Slack posts (mrkdwn) and canvases, not email or documents
- "Open your editor" and IDE-workflow references stripped
- Tool references genericized to "connected workspace tools" rather than hardcoded tool names
- Anthropic company-specific examples removed
- Scheduler-pairing note added where recurrence is natural

## Apache-2.0 notice

The vendored reference files in `references/` are derived from upstream content licensed under the Apache License, Version 2.0. A copy of that license is in `LICENSE.txt` in this directory.
