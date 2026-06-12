---
name: marketing-analytics
description: Use when asked to analyze marketing performance data — campaign ROI, channel attribution, traffic trends, conversion funnels, or CAC/LTV — and surface which bets are working and which aren't.
metadata:
  version: 1.0.0
  display_name: Marketing Analytics
  tags: marketing, analytics, ROI, attribution, CAC, LTV, funnel, campaign
---

## Goal

Turn marketing numbers into one clear verdict: what's working, what isn't, and what to change next.

## Steps

1. **Clarify scope** — which channel(s), what time period, what decision this informs (budget allocation? campaign kill/keep? board update?).
2. **Gather the data** — accept pasted tables, CSV uploads, or use connected analytics tools if available via Composio. Note the data source and freshness.
3. **Calculate the core metrics** for the scope — see `references/marketing-metrics.md`. Don't calculate metrics for which you lack clean inputs.
4. **Identify the signal** — what's outperforming? What's underperforming? Is the trend directional or noise? Use week-over-week or month-over-month deltas.
5. **Write the verdict** — one sentence per channel: "Paid social: CAC $142, trending up 18% MoM — at risk of exceeding LTV threshold." Then 2-3 so-what bullets for the decision-maker.
6. **Deliver** — post verdict + bullets to Slack. Offer the full breakdown as a canvas or file.

## Rules

- Never average percentages directly (average conversion rate across campaigns ≠ total conversions / total impressions — compute from raw if possible).
- Attribution models change what's "working" — state which model is in use (last-touch, first-touch, linear). If unknown, say so.
- Distinguish signal from noise: a single-week spike with no correlated event is noise until proven otherwise.
- Do not invent benchmarks. Use workspace facts if industry benchmarks are stored there; otherwise say "no benchmark available".
- Keep the Slack post under 200 words; put tables in the canvas.
