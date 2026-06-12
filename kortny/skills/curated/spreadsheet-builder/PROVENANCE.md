# Provenance

**Concept source**: Anthropic proprietary internal document skills (xlsx / spreadsheet authoring)
**Script authorship**: Original (clean-room rewrite)
**Adaptation date**: 2026-06-12
**Adapted by**: Agent D (HIG-239)

## What was adapted

The SKILL.md was written fresh. The script (`build_workbook.py`) is an
original implementation using openpyxl — no code or wording was copied from
the upstream source. The upstream skill is proprietary; only the
*professional standards* (which are unprotectable ideas) informed this skill:
zero formula errors, financial color-coding (green positive / red negative),
correct per-column number formats, and frozen header rows.

## Script dependencies

- `build_workbook.py`: openpyxl only. argparse, JSON spec in (file or stdin),
  `.xlsx` file out, no network access.

## Slack-first adaptations

- Output targets a Slack file upload (the workbook itself), not an IDE save.
- File paths use workbench paths, not local development paths.
- No `.claude/` or editor assumptions; brand/format conventions are pulled
  from known workspace facts in prose, not from local config files.

## License

Original concept source is proprietary — this skill and script are a
clean-room rewrite. This file and all files in this directory are subject to
the Kortny project license.
