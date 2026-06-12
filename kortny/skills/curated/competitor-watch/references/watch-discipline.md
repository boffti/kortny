# Watch discipline — storing and diffing snapshots

The watch is only as good as the baseline you compare against. Be deliberate
about what "last seen" means.

## What to capture per page, per run

For each watched surface keep a compact snapshot in the run summary so the next
run can diff against it:

- **Pricing pages:** tier names, the headline price per tier, billing unit
  (per-seat / usage / flat), seat minimums, and any "most popular" badge.
- **Changelog / release notes:** the title and date of the most recent entry
  (and the last few), so a new entry is obvious next time.
- **Blog:** title + date of the latest post(s).
- **Homepage / positioning:** the hero headline and primary tagline — these
  change rarely but matter most when they do.

Keep it to the facts that change, not the whole page. The snapshot lives in the
run output, which becomes the next run's baseline via episodes.

## Finding the baseline

1. **Kortny's previous watch run** in episodes / prior thread context — the
   cleanest baseline. Diff current state against the snapshot it recorded.
2. **No prior run** → this is a baseline run. Capture current state, report it as
   "establishing baseline — watching from here", and don't claim changes you
   can't substantiate.

## Diffing rules

- Compare **like to like**: this run's pricing snapshot vs last run's pricing
  snapshot, this run's latest changelog title vs last run's.
- A **new changelog/blog entry** = entries present now that weren't in the last
  snapshot. Report the new ones only.
- A **pricing change** = any captured field that differs. Always report
  `old → new`.
- A **positioning change** = hero headline or tagline differs. Quote both.
- **Cosmetic churn** (reworded marketing copy with the same meaning, reordered
  sections) is not a change — don't report it. Substance over wording.

## When a fetch fails

A page that couldn't be loaded (403, moved, paywalled, timeout) is **unknown**,
not unchanged. Report it explicitly as "couldn't verify this run, will retry"
and keep the prior snapshot as the baseline. Never let a failed fetch collapse
into a false "no changes".

## Pairing with article-extractor and web search

- Use **web search** to confirm or rediscover URLs (competitors move pages) and
  to catch coverage the team should see (a funding announcement, a launch on a
  news site).
- Use the **article-extractor** skill to pull clean text from a fetched page —
  it strips navigation and boilerplate so the diff reflects real content, not
  template noise.
