# Comparison and anomaly conventions

The whole value of a digest is the comparison. Get the deltas right.

## Picking the baseline

In priority order:

1. **Kortny's previous digest** (prior thread context or episodes). Reuse its
   exact metric names and numbers as the "from" side so deltas are honest and
   wording stays stable across runs.
2. **A prior period inside the dataset** — last week's rows vs this week's,
   last month vs this month. Match like for like (a full week vs a full week,
   not a full week vs a partial one).
3. **Targets/expected ranges from workspace facts** — when there's no prior run
   but the team has stated a goal ("target activation 50%"), compare to that.
4. **No baseline** → say so. Report current levels, call it the baseline run,
   and the *next* digest does the comparing.

## Deltas

For each tracked metric report:

- **From → To** with units (`41% → 58%`, `$12.1k → $11.4k`).
- **Absolute change** in points or units (`+17pts`, `−$0.7k`).
- **Percent change** *only when the denominator is meaningful*.
- **Direction and streak** when it matters (`down two weeks now`).

Rates and percentages move in **points**, not percent: 41% → 58% is **+17
points**, not "+41%". Stating it as a percent of a percent is the most common
digest error — avoid it.

## Small denominators

A change from 1 to 4 is "+3 (small base)", not "+300%". When the base is under
~30, lead with the absolute number and note the base is small. Percent change on
a tiny base is noise dressed as signal.

## Period alignment

- Week-over-week is the default for weekly digests.
- Call out **same-period-last-year** only when seasonality is in play and the
  data goes back far enough.
- A **partial current period** (digest runs mid-week) must be labeled
  "week to date" and compared to the equivalent partial prior period, never to a
  full week.

## What counts as an anomaly

Flag, in plain terms:

- A metric **outside its usual range** (roughly beyond its recent run of values).
- A **sign flip** — something that was growing is now shrinking.
- A **sudden spike or drop** concentrated in one day/segment.
- A metric that **stopped updating** (same value as last run when it normally
  moves) — likely a broken pipeline, not real stability.

An anomaly is an observation. Offer a probable cause only when the data points
at it (e.g. a spike isolated to one day → "possible one-off incident"). Otherwise
flag it and ask. Never present a guessed cause as fact.
