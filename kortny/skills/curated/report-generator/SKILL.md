---
name: report-generator
description: Use when asked to generate a structured report from data, notes, or research — executive summary, detailed findings, audience-tiered versions — delivered as a Slack mrkdwn post plus a file upload for the full document.
metadata:
  version: 1.0.0
  display_name: Report Generator
  tags: report, executive summary, findings, analysis, audience-tiering, document
---

## Goal

Produce a structured, audience-appropriate report and deliver it where the audience lives — a tight mrkdwn summary in Slack, with the full report as an uploaded file.

## Steps

1. **Clarify scope** — what is the report about? What data, notes, or research inputs are available? Who is the audience and what decision does this report support?
2. **Tier the audience** — use the audience-tiering table in `references/audience-tiers.md` to determine which version(s) to produce.
3. **Draft the report** — structure it per `references/report-structure.md`. Lead every section with the conclusion, not the methodology.
4. **Write the Slack summary** — a tight mrkdwn post with: TL;DR (1 sentence), 3-5 key findings (bullets), and the primary recommendation or next step. Post this to Slack inline.
5. **Produce the full report** — format as clean markdown suitable for upload as a `.md` file (or request styled-report-pdf skill for a PDF version). Upload to Slack as a file.
6. **Offer tiered versions** — if multiple audiences need this (exec vs. team vs. technical), produce the exec version first and offer to adapt.

## Output delivery

- **Slack post**: mrkdwn TL;DR + key findings bullets (always posted inline).
- **File upload**: full report as `.md` (or `.pdf` if styled-report-pdf is available).
- **No HTML output**: Kortny does not serve web pages. PDF via styled-report-pdf; otherwise `.md`.

## Rules

- Conclusions before methodology. Executives read the first 3 bullets; put the finding there.
- Every quantitative claim cites its source or states "based on provided data".
- Do not pad reports with methodology descriptions when the audience is results-focused.
- Use workspace facts for brand voice, product names, and any known audience context.
- Reports > 1000 words belong in the file upload, not the Slack post.
