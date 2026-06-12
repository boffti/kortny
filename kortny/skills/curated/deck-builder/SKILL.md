---
name: deck-builder
description: Use when asked to build, generate, or produce a slide deck, PowerPoint, .pptx, presentation, pitch deck, or board/review deck to upload to Slack — when the deliverable is an actual slide file with a consistent theme and layout, not talking points in a message.
metadata:
  version: 1.0.0
  display_name: Deck Builder
  tags: deck, slides, presentation, powerpoint, pptx, pitch, board deck, review, python-pptx
---

## Goal

Produce a `.pptx` deck that reads as one coherent document — one idea per
slide, a single theme applied throughout, generous margins — and upload it to
the Slack thread.

## Steps

1. **Outline the deck before building.** One idea per slide. Write each slide
   title as a sentence that states the takeaway ("Signups doubled after the
   referral launch"), not a label ("Signups"). Decide the section breaks.
2. **Pick the theme once.** Choose a single accent color and stick to it for
   every slide. If `theme-factory` has produced a palette for this workspace,
   or known workspace facts describe the brand color, use it — otherwise pick
   one restrained accent and keep it consistent.
3. **Choose a layout per slide:** `title` (cover), `section` (divider),
   `bullets` (max 6 bullets — if you need more, split the slide), `two_col`
   (two bullet columns), `quote` (pull-quote + attribution).
4. **Build with the script** (`scripts/build_deck.py`) by passing a JSON spec.
   It produces a 16:9 deck, applies the theme to every slide, enforces the
   bullet cap and the margins, and anchors a source line to any data slide.
5. **Upload the deck to the thread** with a one-line summary of the arc. Offer
   to render a leave-behind PDF (`styled-report-pdf`) or to drop a chart
   (`chart-maker`) into a specific slide.

## Layout discipline (non-negotiable)

- **One idea per slide.** If a slide needs more than six bullets or two
  distinct topics, it's two slides.
- **Consistent theme.** Same accent color and the same two font sizes (title
  vs. body) on every slide. The deck should not look like assembled templates.
- **Titles are sentences**, not nouns — the title carries the point even if
  the body is skimmed.
- **Generous margins.** Body text never runs edge to edge; the script keeps a
  fixed margin and wraps text.
- **Cite data slides.** Any slide with numbers carries a source line.

## Pairing

- `theme-factory` → supplies the palette/aesthetic for the `theme.accent`.
- `chart-maker` → produces a PNG you can describe as belonging on a slide.
- `styled-report-pdf` → the prose leave-behind version of the same content.

## Script

- `scripts/build_deck.py` — inputs: `--spec spec.json` (or JSON on stdin),
  `--out deck.pptx`. Builds a 16:9 deck from a list of slides. Supported
  layouts: `title`, `section`, `bullets` (capped at 6), `two_col`, `quote`.
  Theme object: `{accent, title_pt, body_pt}`. Optional per-slide `source`
  footer. Deps: python-pptx. No network. See `references/spec-format.md`.
