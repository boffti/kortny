---
name: cohort-analysis
description: Use when asked to analyze user or customer cohorts — retention curves, churn by cohort, LTV by acquisition channel, or activation rates by signup week — to understand how different groups behave over time.
metadata:
  version: 1.0.0
  display_name: Cohort Analysis
  tags: cohort, retention, churn, LTV, activation, product analytics, user behavior
---

## Goal

Surface how different customer cohorts behave over time — which cohorts retain, which churn, and what that means for the business.

## Steps

1. **Clarify the cohort definition** — what groups the cohort? (Signup week/month, acquisition channel, plan tier, onboarding path, feature used.) Confirm the metric being tracked (retention, activation, LTV, feature adoption).
2. **Accept the data** — pasted cohort table, CSV upload, or data from a connected analytics tool. Note the data source and period covered.
3. **Compute the key metrics** — see `references/cohort-metrics.md` for formulas. Do not compute metrics you don't have clean inputs for.
4. **Identify the signal** — where does retention diverge between cohorts? At what time period does churn accelerate? Which acquisition cohorts have the best LTV trajectory?
5. **Produce the insight** — one-paragraph narrative of what the cohort data says, then 2-3 action-oriented bullets. Avoid describing the table; explain what it means.
6. **Deliver** — post narrative + bullets to Slack. Offer the cohort table as a file or canvas for teams who want to drill in.

## Rules

- Cohort analysis requires real timestamped event data — do not run it on aggregate snapshots.
- Always state the cohort definition before conclusions: "June signups who activated within 7 days retained at 62% at month 3."
- Distinguish cohort size effects: a cohort of 8 users telling a different story from a cohort of 800 is noise, not signal.
- If the data period is short (< 3 months), label long-term retention conclusions as provisional.
- Do not extrapolate LTV from fewer than 2 data points per cohort.
