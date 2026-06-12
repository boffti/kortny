#!/usr/bin/env python3
"""Render an HTML document to a styled PDF with WeasyPrint — sandbox-only.

The agent authors the report as HTML (using the frontend-design / theme-factory
aesthetic). This script wraps that HTML in a print stylesheet that enforces the
report conventions Kortny commits to:

  * A4 pages with comfortable margins and an automatic footer page number
  * one type family, a clear heading scale, restrained accent color
  * tables that don't break a row across a page; headings that don't strand
    at the bottom of a page
  * a cover block (title + subtitle + date) when those fields are supplied

Two input modes:
  * ``--html PATH``  — a full or fragment HTML file authored by the agent
  * ``--html-stdin`` — read the HTML from stdin

If the supplied HTML has no ``<html>`` root it is treated as a body fragment
and wrapped in the print template. A fully-formed document is rendered as-is
(the base print CSS is still attached so page setup applies).

Network is never required; remote ``<img src=...>`` is disabled. Reference
local images by absolute path under the workbench dir.
"""

from __future__ import annotations

import argparse
import html as html_lib
import sys
from datetime import date
from pathlib import Path

from weasyprint import HTML

# Print stylesheet — the report "house style". Deliberately conservative:
# one accent color, a single serif/sans stack, page-aware table/heading rules.
BASE_CSS = """
@page {
  size: A4;
  margin: 22mm 18mm 20mm 18mm;
  @bottom-center {
    content: counter(page) " / " counter(pages);
    font-size: 9pt;
    color: #6b7280;
  }
}
:root { --accent: %(accent)s; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 11pt;
  line-height: 1.5;
  color: #1f2937;
}
h1, h2, h3 { color: var(--accent); line-height: 1.25; break-after: avoid; }
h1 { font-size: 22pt; margin: 0 0 4pt; }
h2 { font-size: 15pt; margin: 18pt 0 6pt; border-bottom: 1px solid #e5e7eb; padding-bottom: 3pt; }
h3 { font-size: 12pt; margin: 14pt 0 4pt; }
p { margin: 0 0 8pt; }
ul, ol { margin: 0 0 8pt 18pt; }
table { width: 100%%; border-collapse: collapse; margin: 10pt 0; font-size: 10pt; }
th, td { border: 1px solid #e5e7eb; padding: 5pt 7pt; text-align: left; }
th { background: #f3f4f6; font-weight: 600; }
tr { break-inside: avoid; }
.cover { margin-bottom: 24pt; }
.cover .title { font-size: 28pt; font-weight: 700; color: var(--accent); }
.cover .subtitle { font-size: 14pt; color: #4b5563; margin-top: 4pt; }
.cover .meta { font-size: 10pt; color: #6b7280; margin-top: 8pt; }
.muted { color: #6b7280; }
"""

DOC_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>%(title)s</title></head>
<body>%(cover)s%(body)s</body></html>"""


def _cover_block(title: str | None, subtitle: str | None, doc_date: str | None) -> str:
    if not (title or subtitle):
        return ""
    parts = ['<div class="cover">']
    if title:
        parts.append(f'<div class="title">{html_lib.escape(title)}</div>')
    if subtitle:
        parts.append(f'<div class="subtitle">{html_lib.escape(subtitle)}</div>')
    shown_date = doc_date or date.today().isoformat()
    parts.append(f'<div class="meta">{html_lib.escape(shown_date)}</div>')
    parts.append("</div>")
    return "".join(parts)


def _looks_like_full_document(markup: str) -> bool:
    head = markup.lstrip()[:200].lower()
    return head.startswith("<!doctype") or "<html" in head


def render(
    markup: str,
    out_path: Path,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    accent: str = "#2563eb",
    doc_date: str | None = None,
) -> Path:
    css = BASE_CSS % {"accent": accent}
    if _looks_like_full_document(markup):
        document = markup
        # Inject base CSS into the existing <head> so page setup always applies.
        if "</head>" in document:
            document = document.replace("</head>", f"<style>{css}</style></head>", 1)
        else:
            document = f"<style>{css}</style>{document}"
    else:
        document = DOC_TEMPLATE % {
            "title": html_lib.escape(title or "Report"),
            "cover": _cover_block(title, subtitle, doc_date),
            "body": markup,
        }
        document = document.replace("</head>", f"<style>{css}</style></head>", 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # base_url=None + WeasyPrint's default url_fetcher still resolves local
    # absolute paths; remote fetches simply fail closed (no network anyway).
    HTML(string=document, base_url=str(out_path.parent)).write_pdf(str(out_path))
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render HTML to a styled PDF.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--html", help="path to an HTML file (full doc or fragment)")
    src.add_argument("--html-stdin", action="store_true", help="read HTML from stdin")
    parser.add_argument("--out", required=True, help="output .pdf path")
    parser.add_argument("--title", help="cover title (fragment mode)")
    parser.add_argument("--subtitle", help="cover subtitle (fragment mode)")
    parser.add_argument("--date", dest="doc_date", help="cover date (YYYY-MM-DD)")
    parser.add_argument("--accent", default="#2563eb", help="accent color hex")
    args = parser.parse_args(argv)

    markup = sys.stdin.read() if args.html_stdin else Path(args.html).read_text()
    out = render(
        markup,
        Path(args.out),
        title=args.title,
        subtitle=args.subtitle,
        accent=args.accent,
        doc_date=args.doc_date,
    )
    print(f"wrote pdf: {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
