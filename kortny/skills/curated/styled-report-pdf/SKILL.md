---
name: styled-report-pdf
description: Use when asked to produce a polished PDF report, formatted document, one-pager, brief, or leave-behind to upload to Slack — when the deliverable is a styled, print-ready PDF with a cover, headings, and tables, not plain text in a message.
metadata:
  version: 1.0.0
  display_name: Styled Report PDF
  tags: pdf, report, document, one-pager, brief, leave-behind, weasyprint, html, print
---

## Goal

Produce a print-ready PDF that looks designed — a cover block, a clear
heading scale, clean tables, automatic page numbers — and upload it to the
Slack thread.

## Approach

You author the report as HTML, then render it to PDF with WeasyPrint. The
render script attaches a print stylesheet (the "house style") so you focus on
content and structure, not on page setup.

## Steps

1. **Write the report as HTML** using the `frontend-design` aesthetic — real
   semantic structure (`<h1>`/`<h2>`/`<h3>`, `<p>`, `<ul>`, `<table>`), not a
   wall of `<div>`s. You can author a body fragment (the script wraps it and
   adds the cover) or a full document (the script renders it and still applies
   page setup).
2. **Apply the brand aesthetic.** Pass `--accent` (and let `theme-factory` or
   known workspace facts pick the brand color). The base stylesheet handles
   typography, table borders, spacing, and page margins.
3. **Render with the script** (`scripts/render_pdf.py`). For a fragment, pass
   `--title` / `--subtitle` / `--date` to get a cover block. The script
   produces A4 pages with a `page / pages` footer, keeps table rows from
   splitting across a page, and keeps headings from stranding at a page
   bottom.
4. **Upload the PDF to the thread** with a one-line summary. Offer a slide
   version (`deck-builder`) or the underlying data as a workbook
   (`spreadsheet-builder`).

## Layout discipline (non-negotiable)

- **A consistent house style** — one type family, a clear `h1`/`h2`/`h3`
  scale, one restrained accent color. No mixing fonts or accent colors.
- **Page-aware layout** — table rows never break across a page; a heading
  never strands alone at the bottom of a page; every page is numbered.
- **A cover block** with title, optional subtitle, and date for any report
  longer than a page.
- **Tables explained in prose.** A table supports the text; it does not
  replace it.
- **Local images only.** Reference images by absolute path under the
  workbench dir — there is no network at render time.

## Pairing

- `frontend-design` → the HTML structure and visual quality.
- `theme-factory` → the accent color / aesthetic.
- `chart-maker` → produce a PNG, save it under the workbench dir, and embed it
  with `<img src="/abs/path.png">`.

## Script

- `scripts/render_pdf.py` — inputs: `--html file.html` **or** `--html-stdin`,
  plus `--out report.pdf`. Fragment-mode extras: `--title`, `--subtitle`,
  `--date YYYY-MM-DD`, `--accent "#2563eb"`. A fragment (no `<html>` root) is
  wrapped in the print template with a cover; a full document is rendered with
  the print CSS injected. Deps: weasyprint (needs the pango/cairo system libs
  baked into the sandbox image). No network. See `references/authoring.md`.
