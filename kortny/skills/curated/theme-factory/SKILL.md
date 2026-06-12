---
name: theme-factory
description: Use when asked to create, adapt, or apply a visual theme — color palette, typography system, component tokens — for a product, document, or presentation.
metadata:
  version: 1.0.0
  display_name: Theme Factory
  tags: theme, color, palette, typography, tokens, design-system, branding, visual
---

## Goal

Produce a coherent, reusable visual theme: color palette + typography + spacing tokens, ready to drop into CSS, a slide deck, or a design tool.

## Steps

1. **Gather inputs**: brand colors (hex or description), mood/adjectives (trustworthy, bold, minimal), intended medium (web, slides, doc, Slack canvas). Use known workspace facts about the product/brand if present.
2. **Build the palette**:
   - Primary (2 shades), Secondary (2 shades), Neutral scale (6 steps from near-white to near-black), Semantic (success green, warning amber, error red, info blue).
   - Check contrast: primary on white must pass WCAG AA (4.5:1 body text; 3:1 large text).
   - See `references/palette-construction.md` for the generation method.
3. **Select type scale**: 1 heading face, 1 body face (system or Google Font), 5 sizes (xs/sm/base/lg/xl), matching line-heights.
4. **Emit tokens** in the requested format:
   - CSS custom properties (`:root { --color-primary: … }`) for web.
   - Named swatches table for slides/docs.
5. **Showcase**: produce a one-page HTML preview (`assets/showcase.html` or inline code) demonstrating the palette and type scale together.
6. **Offer Slack delivery**: post the palette as a formatted Slack message with hex swatches in code blocks, and offer to upload the HTML showcase as a file.

## Pre-built themes

Ten named themes are defined in `references/themes.md`. Each has a 4-color palette with hex codes, a typography pairing, and recommended use cases. When a user selects or asks for one of the named themes, load the corresponding section from that file and apply it directly without re-generating the palette from scratch.

Available themes: Ocean Depths, Sunset Boulevard, Forest Canopy, Modern Minimalist, Golden Hour, Arctic Frost, Desert Rose, Tech Innovation, Botanical Garden, Midnight Galaxy.

## Rules

- Never ship a palette where primary and secondary are too close in hue (ΔH < 30°) unless the brief explicitly asks for monochrome.
- Always name every token; unnamed colors are not a system.
- If the brand color fails WCAG AA, say so and propose the nearest compliant adjustment rather than silently changing it.
