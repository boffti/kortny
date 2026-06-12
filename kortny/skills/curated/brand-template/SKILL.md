---
name: brand-template
description: Use when asked to apply brand guidelines to a document, message, or artifact — ensuring the right tone of voice, color use, logo placement rules, and typography are followed — or to create a fill-in brand template for the workspace.
metadata:
  version: 1.0.0
  display_name: Brand Template
  tags: brand, brand-guidelines, tone-of-voice, template, identity, style, voice, messaging
---

## Goal

Apply consistent brand identity to any output — or produce a reusable brand template anchored to the workspace's known facts.

## Steps

1. **Locate brand inputs**: check known workspace facts first (product name, brand colors, tone descriptors, voice examples). If none are present, ask for the three most important brand rules before proceeding.
2. **Choose the task mode**:
   - *Apply brand to existing content* → rewrite the content through the brand lens (tone, vocabulary, preferred phrasings). See `references/tone-guide.md` for the default voice spectrum.
   - *Create a fill-in brand template* → produce a structured template with labelled sections and `[FILL: …]` prompts for brand-specific details.
   - *Audit content for brand compliance* → check against the rules in `references/brand-checklist.md` and flag deviations with suggested fixes.
3. **For tone adaptation**: match the voice descriptors (e.g. "direct but warm", "technical but approachable"). See `references/tone-guide.md` for patterns.
4. **For visual templates** (slides, docs, canvases): apply colors and typography from workspace facts or the `theme-factory` skill output if available.
5. **Deliver**: Slack message for short-form output; canvas or uploaded file for templates and longer docs.

## Output

- For content rewrites: show the original and adapted version side by side in a Slack thread for review.
- For templates: emit the full template with clear `[FILL: …]` prompts and a one-line explanation of each section's purpose.
- For audits: bullet list of deviations, ordered by severity, each with a one-line fix.

## Rules

- Never invent brand rules. If the workspace has no known brand facts, state that you are working from generic professional defaults and invite correction.
- Do not overwrite a brand template without confirming the replacement — canvas edits are visible.
- Tone guidance takes precedence over personal style preferences — if the brand says "no exclamation marks", enforce it even if the requester uses them.
