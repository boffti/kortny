---
name: revops
description: Use when asked to analyze pipeline health, forecast revenue, audit CRM data quality, build a sales funnel report, or answer revenue operations questions about conversion rates, deal velocity, or quota attainment.
metadata:
  version: 1.0.0
  display_name: Revenue Operations (RevOps)
  tags: revops, revenue, pipeline, CRM, forecast, funnel, sales ops
---

## Goal

Surface the one revenue insight that drives the next decision — pipeline gap, conversion bottleneck, or attainment risk — before the weekly call.

## Steps

1. **Clarify the question** — pipeline review? forecast call prep? funnel audit? quota attainment? Each has a different shape. Confirm the time period and the audience.
2. **Pull the data** — use connected CRM tools (HubSpot, Salesforce via Composio if available) or ask the user to paste the export. Note the data freshness timestamp.
3. **Calculate the key metrics** relevant to the question — see `references/revops-metrics.md` for formulas.
4. **Find the bottleneck or gap** — where in the funnel is conversion lowest? Where is pipeline thinnest vs. quota? What's the close-rate trend?
5. **Draft the output** — post a Slack summary with: the headline number, the bottleneck identified, 2-3 data-backed bullets, and a "so what / recommended action".
6. **Offer the detail** — for large datasets, offer a file upload or canvas with the full breakdown.

## Rules

- Lead with the number that changes a decision; don't bury it in context.
- Distinguish actuals from projections. Forecast numbers carry a confidence range or caveat.
- Never round pipeline numbers into false precision. "$2.1M" from "$2,073,400" is fine; "$2M" from "$1,800,000" is not.
- If CRM data has gaps or stale close dates, flag it before drawing conclusions.
- Use workspace facts for context about the team, quota periods, or named accounts if present in Kortny's knowledge graph.
