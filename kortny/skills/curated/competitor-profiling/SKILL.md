---
name: competitor-profiling
description: Use when asked to build a detailed profile or dossier on a specific competitor — their product, positioning, pricing, team, funding, and recent moves. Distinct from competitive-analysis (which compares a landscape); this skill goes deep on one company.
metadata:
  version: 1.0.0
  display_name: Competitor Profiling
  tags: competitor, profile, dossier, research, intelligence
---

## Goal

Produce a single-company intelligence dossier — the depth a BD or product team needs before a competitive deal or product decision, not a side-by-side table.

## When to use this vs. competitive-analysis

Use **competitor-profiling** when you want to go deep on *one* company: their full product surface, leadership, funding history, go-to-market, and recent signals.
Use **competitive-analysis** when you want to compare *multiple* competitors across shared dimensions.

## Steps

1. **Confirm scope** — name of the company, what angle matters (product, pricing, GTM, hiring signals, or all). If not specified, do all.
2. **Research — company basics**: founding year, HQ, employee count (LinkedIn or Crunchbase signals), funding rounds and lead investors, revenue signals (press, benchmarks), and key leadership.
3. **Research — product**: core product surface, pricing page (screenshot in prose if paywalled), notable integrations, recent releases or changelog entries, tech stack signals (job postings, BuiltWith, docs).
4. **Research — GTM**: ICP and stated positioning, primary channels (paid, SEO, events, partnerships), notable customer logos, case studies tone.
5. **Research — momentum**: recent news (last 90 days), job postings trajectory (growing which functions?), G2/Reddit/Hacker News signal on sentiment.
6. **Structure the dossier** — use the template in `references/dossier-template.md`.
7. **Close with intelligence gaps** — list what you couldn't find and the best next source for each.

## Rules

- Date every claim. Undated market-share or pricing numbers must be flagged "date unknown".
- Separate confirmed facts from inference. Use "appears to" or "signals suggest" for inferred conclusions.
- Use workspace facts (known from Kortny's graph context) about your own product and positioning when making comparisons — do not invent your own product's details.
- No fabricated funding or headcount numbers — if not public, say so.
- Keep dossier under 600 words in the Slack post; offer the full version as a canvas or thread.
