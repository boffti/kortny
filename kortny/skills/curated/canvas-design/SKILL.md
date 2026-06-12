---
name: canvas-design
description: Use when asked to design or lay out a Slack canvas — structured reference docs, project briefs, decision records, onboarding guides, or any long-form content intended to live as a canvas rather than a thread message.
metadata:
  version: 1.0.0
  display_name: Canvas Design
  tags: canvas, layout, document, reference, structured, design, slack-canvas, brief
---

## Goal

Produce a canvas that is genuinely useful as a persistent reference — not a reformatted chat message, but a document a new team member could read and act on.

## Steps

1. **Identify the canvas type** from the request:
   - *Reference doc* (policy, runbook, FAQ) — headers, numbered steps, definitions block.
   - *Project brief* — goal, scope, stakeholders, timeline, open questions.
   - *Decision record* — context, options considered, decision, rationale, consequences.
   - *Onboarding guide* — ordered steps, role-specific sections, links to resources.
2. **Structure before prose**: outline the H1 → H2 → H3 hierarchy first. Each section should have one purpose.
3. **Draft in Slack canvas markdown**: H1 headings, bold section labels, bullet lists, code blocks where applicable. See `references/canvas-conventions.md` for the element set Slack canvases support.
4. **Apply the typography and spacing discipline** from the canvas conventions reference — use known workspace brand or product facts to fill in any company-specific details.
5. **Offer**: post the canvas content as a Slack message for review first, then create or update the canvas once confirmed.

## Rules

- Canvases are reference material; do not write in the first person or use chat-style language.
- Every section header must be meaningful — no "Section 1", "Overview of Overview".
- Keep a canvas under ~1,500 words unless it is an explicit reference library. Longer content goes in a linked sub-canvas or uploaded file.
- No placeholder text left in the final output — if a detail is unknown, use a labelled `[FILL: …]` prompt.
