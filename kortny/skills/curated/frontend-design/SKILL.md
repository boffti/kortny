---
name: frontend-design
description: Use when asked to design, critique, or build a UI component, landing page, or web interface — including producing HTML/CSS mockups, reviewing designs for accessibility and visual clarity, or generating implementation-ready code snippets.
metadata:
  version: 1.0.0
  display_name: Frontend Design
  tags: ui, ux, html, css, design, component, mockup, accessibility, web, interface
---

## Goal

Produce implementation-quality frontend designs or reviews — not wireframe descriptions, but code or actionable critique.

## Steps

1. **Understand the context first**: what is the page/component for, who uses it, what does success look like? If designing from scratch, ask for the key user action before writing a line of code.
2. **Choose the output format**:
   - *Mockup request* → produce clean semantic HTML + CSS (no external frameworks unless asked). Use CSS custom properties for theming.
   - *Review request* → work through the design against the checklist in `references/review-checklist.md`.
   - *Code snippet* → focus on the specific component; include accessibility attributes.
3. **Apply design discipline**: see `references/design-principles.md` for spacing, contrast, type scale, and motion rules. For richer aesthetic direction — design philosophy, type pairing strategy, the two-pass brainstorm/critique/build process, and how to avoid default design patterns — see `references/aesthetics.md`.
4. **Accessibility first**: every interactive element has a keyboard focus state, ARIA label where needed, and sufficient color contrast (WCAG AA minimum).
5. **Deliver as a Slack file** when the HTML mockup is more than ~30 lines; otherwise paste inline with a code fence.

## Rules

- No inline styles for anything other than dynamic values.
- Never ship a button without a visible focus ring.
- Prefer `rem` for font sizes, `px` for borders and shadows.
- If using a color, name it via a CSS custom property (`--color-primary`), not a hex literal.
- When reviewing: name the issue, the standard it violates, and the one-line fix. Do not pad a review to seem thorough.
