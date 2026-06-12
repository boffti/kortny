# Provenance

**Concept source**: Anthropic proprietary internal document skills (pdf / report authoring)
**Script authorship**: Original (clean-room rewrite)
**Adaptation date**: 2026-06-12
**Adapted by**: Agent D (HIG-239)

## What was adapted

The SKILL.md was written fresh. The script (`render_pdf.py`) and its embedded
print stylesheet are an original implementation using WeasyPrint — no code or
wording was copied from the upstream source. The upstream skill is
proprietary; only the *layout standards* (unprotectable ideas) informed this
skill: a consistent house style, page-aware tables and headings, a cover
block, and automatic page numbers.

## Script dependencies

- `render_pdf.py`: weasyprint only. Requires the pango / cairo system
  libraries (baked into the sandbox image). argparse, HTML in (file or stdin),
  `.pdf` file out, no network access (remote images fail closed).

## Slack-first adaptations

- Output targets a Slack file upload (the PDF itself).
- Aesthetic / accent color sourced from `frontend-design` + `theme-factory` or
  known workspace facts, not a local config file.
- Images are referenced by absolute workbench path (no network at render
  time); file paths use workbench paths, not local development paths.

## License

Original concept source is proprietary — this skill and script are a
clean-room rewrite. This file and all files in this directory are subject to
the Kortny project license.
