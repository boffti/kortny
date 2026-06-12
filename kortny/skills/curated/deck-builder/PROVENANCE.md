# Provenance

**Concept source**: Anthropic proprietary internal document skills (pptx / presentation authoring)
**Script authorship**: Original (clean-room rewrite)
**Adaptation date**: 2026-06-12
**Adapted by**: Agent D (HIG-239)

## What was adapted

The SKILL.md was written fresh. The script (`build_deck.py`) is an original
implementation using python-pptx — no code or wording was copied from the
upstream source. The upstream skill is proprietary; only the *layout
discipline standards* (unprotectable ideas) informed this skill: one idea per
slide, a single consistent theme, sentence-style titles, generous margins,
and cited data slides.

## Script dependencies

- `build_deck.py`: python-pptx only. argparse, JSON spec in (file or stdin),
  `.pptx` file out, no network access.

## Slack-first adaptations

- Output targets a Slack file upload (the deck itself).
- Theme accent is sourced from `theme-factory` output or known workspace
  facts (brand color) rather than a local config file.
- File paths use workbench paths, not local development paths.

## License

Original concept source is proprietary — this skill and script are a
clean-room rewrite. This file and all files in this directory are subject to
the Kortny project license.
