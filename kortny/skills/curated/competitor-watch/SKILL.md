---
name: competitor-watch
description: Use when asked to watch a competitor, monitor a rival's changelog or pricing or blog, keep tabs on what competitors are shipping, or get alerted when a competitor changes something — fetch their pages, diff against what was seen last time, and report only what actually changed.
metadata:
  version: 1.0.0
  display_name: Competitor Watch
  tags: competitor, monitor, watch, changelog, pricing, changes, tracking
---

## Goal

Keep an eye on competitors over time and surface *changes* — a new feature shipped, a pricing tweak, a positioning shift, a notable post — without re-summarizing things the team already saw.

This is monitoring, not analysis. `competitive-analysis` produces a one-time analyst assessment ("how do we stack up"). `competitor-watch` runs on a cadence and reports the **diff** since last run. If nothing changed, the right output is "no changes" — that discipline is the feature.

## Steps

1. **Establish the watchlist and the pages.** Which competitors, and which surfaces — pricing page, changelog/release notes, blog, homepage hero, careers (hiring signals). Pull the watchlist from the request, prior thread context, or **workspace facts** if the team recorded one.
2. **Fetch current state.** Use **web search** to find/confirm the right URLs, and pair with the **article-extractor** skill to pull clean page text (it strips nav/boilerplate so the diff is meaningful). For changelogs and blogs, fetch the latest entries; for pricing, fetch the current tiers and numbers.
3. **Find the last-seen baseline.** Look in **episodes** and prior thread context for Kortny's previous watch run — the prior summary of each page is what you diff against. See `references/watch-discipline.md` for what to store and how to compare when there's no exact prior snapshot.
4. **Diff, don't re-describe.** Compare current state to last-seen. A change is: a new changelog/blog entry, a pricing number or tier that moved, a new or removed feature claim, a positioning/tagline shift. Unchanged pages produce nothing.
5. **Report only the changes**, each with: competitor, what changed, the old → new where it's a value (price, tier name, tagline), the source link, and a one-line "so what" for the team only when it's clearly material.
6. **If nothing changed across the whole watchlist**, say exactly that in one line — don't manufacture observations to fill space.

## Output shape (Slack mrkdwn)

```
*Competitor watch — Jun 12* (since Jun 5)

*Acme*
• Pricing: Pro tier $49 → $39/seat. Source: <link|pricing>. So what: undercuts our Pro by $10.
• Changelog: shipped SSO (was enterprise-gated before). <link|changelog>

*Globex*
• Blog: "Why usage-based beats per-seat" — positioning shift toward our model. <link|post>

_Beta Corp, Initech: no changes._
```

When everything is quiet:

```
*Competitor watch — Jun 12:* no changes across Acme, Globex, Beta Corp, Initech since last week.
```

## Rules

- Only report changes. A page that didn't move gets a one-line "no changes" in the roll-up, never a re-summary.
- Quote the change precisely — old → new for any value. "Pricing changed" without the numbers is useless.
- Every change carries its source link so the team can verify. No source, no claim.
- Don't infer intent. "Acme dropped Pro to $39" is a fact; "Acme is panicking about us" is a guess — keep guesses out, or clearly label a single "so what" as inference.
- If a page couldn't be fetched (blocked, moved, paywalled), say so for that competitor rather than silently dropping it — a missed fetch is not "no changes".
- Built to run on a schedule — pair with Kortny's scheduler for "check competitors every Monday". The scheduled cadence is what makes the diffing automatic and the "since last run" honest.

## Worked example

Scheduled Friday watch over a 3-competitor list, prior run in episodes:

> *Competitor watch — Jun 12* (since Jun 5)
>
> *Acme*
> • Pricing: Team tier seat minimum 5 → 3. <https://acme.example/pricing|source>. So what: lowers their entry point, more competitive for small teams.
>
> *Globex*
> • Changelog: launched an API (previously "coming soon"). <https://globex.example/changelog|source>.
>
> _Initech: no changes. Beta Corp: pricing page returned 403 — couldn't verify, will retry next run._
