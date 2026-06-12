# Provenance

**Base SKILL.md**: Kortny-authored (Agent A, HIG-239, 2026-06-12) — original prose; canvas-design repurposed for Slack canvases (not visual art PDFs). Retained as primary body.
**References and assets vendored from**: https://github.com/anthropics/skills, commit `57546260929473d4e0d1c1bb75297be2fdfa1949`, 2026-06-12.
**Vendored by**: Agent F (HIG-239 corrective pass)

## License verification

Directory `skills/canvas-design/LICENSE.txt` in upstream repo is Apache-2.0 (verified per-dir). Font files carry per-family OFL (SIL Open Font License 1.1) licenses — each included as `<Family>-OFL.txt` alongside the `.ttf` files.

## What was vendored

| File / Path | Upstream source | Adaptations |
|---|---|---|
| `references/design-principles.md` | `skills/canvas-design/SKILL.md` (upstream's visual-art philosophy) | Distilled into a reference file; re-framed for Kortny context; "canvas" ambiguity resolved (upstream = PDF art; Kortny = Slack canvas); philosophical examples retained; font-path reference updated to local `assets/fonts/` |
| `assets/fonts/Lora-*.ttf` (4 files) | `skills/canvas-design/canvas-fonts/Lora-*.ttf` | Unmodified |
| `assets/fonts/Lora-OFL.txt` | `skills/canvas-design/canvas-fonts/Lora-OFL.txt` | Unmodified |
| `assets/fonts/BricolageGrotesque-*.ttf` (2 files) | `skills/canvas-design/canvas-fonts/BricolageGrotesque-*.ttf` | Unmodified |
| `assets/fonts/BricolageGrotesque-OFL.txt` | `skills/canvas-design/canvas-fonts/BricolageGrotesque-OFL.txt` | Unmodified |
| `assets/fonts/GeistMono-*.ttf` (2 files) | `skills/canvas-design/canvas-fonts/GeistMono-*.ttf` | Unmodified |
| `assets/fonts/GeistMono-OFL.txt` | `skills/canvas-design/canvas-fonts/GeistMono-OFL.txt` | Unmodified |
| `assets/fonts/Gloock-Regular.ttf` | `skills/canvas-design/canvas-fonts/Gloock-Regular.ttf` | Unmodified |
| `assets/fonts/Gloock-OFL.txt` | `skills/canvas-design/canvas-fonts/Gloock-OFL.txt` | Unmodified |
| `assets/fonts/Outfit-*.ttf` (2 files) | `skills/canvas-design/canvas-fonts/Outfit-*.ttf` | Unmodified |
| `assets/fonts/Outfit-OFL.txt` | `skills/canvas-design/canvas-fonts/Outfit-OFL.txt` | Unmodified |

## Font selection rationale (5 families, 11 TTF files, 1.07MB)

Upstream ships 30+ font families (~5.5MB total). Selected 5 that provide maximum range within the 1.2MB cap:

| Family | Role | Size |
|---|---|---|
| Lora (4 variants) | Editorial serif — headlines, body text for formal docs | 534KB |
| BricolageGrotesque (2 variants) | Modern grotesque sans — UI-adjacent, contemporary | 177KB |
| GeistMono (2 variants) | Monospace — code, data, systematic layouts | 152KB |
| Gloock (1 variant) | Display serif — elegant one-weight display face | 92KB |
| Outfit (2 variants) | Geometric sans — clean, versatile, good at scale | 107KB |
| **Total** | | **1,062KB (1.04MB)** |

Families not included: remaining 25+ families exceeded the cap. They are available in upstream `anthropics/skills` and can be added if the cap is raised.

## What was NOT taken from upstream

- Full canvas-fonts directory (30+ families, 5.5MB) — exceeds 1.2MB cap
- No content from any proprietary upstream dirs (docx, pdf, pptx, xlsx, doc-coauthoring)

## Apache-2.0 notice

The vendored content in `references/` and `assets/fonts/` is derived from upstream content licensed under the Apache License, Version 2.0. A copy of that license is in `LICENSE.txt` in this directory. Font files are additionally covered by their respective OFL licenses.
