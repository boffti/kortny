---
name: data-digest
description: Use when asked for a recurring data digest, a "what changed since last time" update, a weekly metrics readout, or a trend/anomaly check on a CSV, spreadsheet, SQL result, or connected data source — compare against the prior run, lead with the deltas, and call out anomalies.
metadata:
  version: 1.0.0
  display_name: Data Digest
  tags: data, digest, recurring, metrics, trends, anomalies, deltas
---

## Goal

Produce a recurring data readout whose value is *comparison*: what moved since last time, what's anomalous, what's worth acting on — across whatever source the data lives in.

This is the recurring, longitudinal cousin of `data-brief`. `data-brief` turns one posted file into a one-shot story for a busy reader. `data-digest` runs again and again on the *same* metrics and earns its keep by comparing this run to the last — deltas, trend direction, anomalies. If there's nothing to compare against (a single dropped file, first-ever look), use `data-brief` instead.

## Steps

1. **Identify the source and the cadence.** Source can be a posted CSV/spreadsheet, a SQL query result, or a connected data tool (a Composio integration like a warehouse, analytics, or BI connector when one is available). Note which it is and the period each run covers.
2. **Find the prior baseline.** This is the whole point. Look, in order, for:
   - the **previous digest** in prior thread context or **episodes** (Kortny's own last run is the cleanest baseline — reuse its numbers and wording);
   - a prior period inside the same dataset (last week's rows vs this week's);
   - **workspace facts** recording targets or expected ranges.
   If no baseline exists, say "first digest — no comparison yet, establishing the baseline" and report levels only.
3. **Compute the deltas** for each tracked metric: absolute and percent change vs the baseline, and the direction. See `references/comparison.md` for the delta and anomaly conventions (what counts as material, how to handle small denominators, week-over-week vs same-period-last-year).
4. **Flag anomalies** — a metric outside its usual range, a sign flip, a sudden spike or drop, a metric that stopped updating. An anomaly gets a one-line "why this might be" only if the data supports it; otherwise just flag it.
5. **Lead with what changed**, not with a full table. The standout movements go first; steady metrics get a single "holding steady" line.
6. **Name the action** if the deltas support one ("retention dropped two weeks running — worth a look before it compounds").

## Output shape (Slack mrkdwn)

```
*Data digest — week of Jun 9* (vs week of Jun 2)

*Moved*
• Activation 41% → 58% (+17pts) — best week this quarter.
• Weekly active 12.1k → 11.4k (−6%) — second week down.

*Anomalies*
• Signup→trial conversion jumped to 22% (usual ~12%) — check the source; possible double-count.

*Holding steady*
• Churn ~3%, NPS 41 — no material change.

*Worth acting on:* the two-week active-user slide. Want the cohort cut?
```

Offer the table or a chart as a follow-up artifact (`chart-maker` / `spreadsheet-builder`) rather than dumping it inline.

## Rules

- Every number is from the data. Never round a guess into a figure, and never fabricate a baseline to manufacture a delta.
- Percent changes need a real denominator — on tiny numbers report the absolute change and say the base is small, don't post a misleading "+300%".
- If the source didn't refresh (same rows as last run), say so plainly: "source hasn't updated since last digest" — a stale digest pretending to be fresh is worse than none.
- Anomaly callouts are observations, not diagnoses. Speculate on cause only when the data points at it; otherwise flag and ask.
- Keep prior-run wording stable so readers can track a metric across digests.
- This is built to run on a schedule — pair with Kortny's scheduler for "post this every Monday"; the body is identical by hand or on schedule, and the scheduled run is what makes the comparison automatic.

## Worked example

Scheduled Monday run over a metrics sheet, prior digest in episodes:

> *Data digest — week of Jun 9* (vs week of Jun 2)
>
> *Moved*
> • Trial→paid 18% → 24% (+6pts) — strongest since March.
> • Weekly active 12.1k → 11.4k (−6%) — down two weeks now.
>
> *Anomalies*
> • Support tickets 90 → 210 (+133%) — spike concentrated on Thursday; possible incident, not a trend.
>
> *Holding steady*
> • MRR growth ~4%/wk, churn ~3%.
>
> *Worth acting on:* the active-user decline and Thursday's ticket spike — they may be the same story. Want me to pull the Thursday cohort?
