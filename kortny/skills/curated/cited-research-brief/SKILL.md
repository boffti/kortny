---
name: cited-research-brief
description: Use when asked to research a topic with sources, write up a briefing with citations, find out what's known about something and back it up, or produce a credible "here's what I found" brief — gather multiple sources, cite every claim inline, weigh source quality, and surface where sources disagree.
metadata:
  version: 1.0.0
  display_name: Cited Research Brief
  tags: research, citations, sources, brief, evidence, fact-check
---

## Goal

Answer a research question with a brief the reader can trust and verify — every
non-obvious claim carries an inline citation, sources are weighed by quality, and
genuine disagreement between sources is surfaced rather than smoothed over.

This is the rigor tier of research. Where `competitive-analysis` and
`data-brief` summarize a known set of inputs, this skill goes out, gathers
multiple independent sources on an open question, and stakes its credibility on
citations and source quality.

## Steps

1. **Pin the question.** Restate what's being asked in one sentence and name the
   decision it informs. If the request is broad, say what you're scoping it to.
2. **Gather multiple independent sources** with **web search** — aim for 3+ that
   don't all trace back to the same origin. Prefer primary sources (the company's
   own docs, the original study, the regulator) over commentary about them. Use
   the **article-extractor** skill to pull clean full text from key pages so you
   quote accurately rather than from a snippet.
3. **Weigh each source.** Apply the quality rubric in
   `references/source-quality.md` — primary vs secondary, recency, independence,
   track record. Note the date of each source; flag anything that may be stale.
4. **Draft claim by claim, citing inline.** Every factual claim gets a citation
   right where it's made. A claim you can't source is either dropped or
   explicitly marked as inference/your own reasoning — never laundered into the
   prose as fact.
5. **Surface disagreement.** When sources conflict, say so plainly: who claims
   what, and which is better-supported and why. Do not average two contradictory
   figures into a fake consensus.
6. **State confidence.** Close with how solid the finding is — well-sourced and
   consistent, thin, or contested — and what would firm it up.
7. **Pick the delivery format by length** (see Output shape).

## Output shape

Short brief (fits comfortably in a message) → post to the **thread** as mrkdwn.
Longer brief, or one the team will revisit → put the body in a **Slack canvas**
and post a short "brief is in the canvas" pointer with the headline finding.

Structure either way:

```
*Question:* Does usage-based pricing reduce churn vs per-seat?

*Bottom line:* Mixed — usage-based correlates with lower logo churn in
self-serve, but the evidence is thinner for sales-led. (confidence: moderate)

*What the sources say*
• Usage-based cuts churn for self-serve SaaS [1][2].
• One large study finds no significant difference once you control for
  contract length [3] — this is the strongest single source.

*Where they disagree*
• [1] and [3] reach opposite conclusions; [3] is larger and controls for
  more variables, so it gets more weight.

*Sources*
[1] OpenView 2025 SaaS Benchmarks — https://… (industry report, Mar 2025)
[2] Vendor blog — https://… (vendor-authored, treat with caution)
[3] Journal of … — https://… (peer-reviewed, n=400, 2024)
```

Inline citation markers are `[1]`, `[2]`, … matched to a numbered Sources list at
the end. Every link is a real URL you actually pulled, not a placeholder.

## Rules

- No claim without a source, or it's flagged as inference. This is the whole
  point of the skill — an uncited assertion in a "cited" brief is a defect.
- Never invent or guess a citation, URL, author, or date. If you can't find a
  source for something, say the evidence is missing.
- Weight by quality, not by count — one rigorous study outweighs three blog posts
  echoing each other. Say which source you trust most and why.
- Surface disagreement explicitly; don't paper over conflicting evidence.
- Note recency on every source and flag stale ones — "as of" matters for fast-
  moving topics.
- State confidence honestly. A thin, contested answer said plainly beats a
  confident-sounding one that the sources don't support.

## Worked example

Request: "research whether four-day work weeks actually keep productivity flat —
with sources."

> *Question:* Do four-day work weeks keep productivity flat?
>
> *Bottom line:* The largest trials report flat-to-up productivity, but they're
> mostly self-selected firms and self-reported metrics — promising, not settled.
> (confidence: moderate)
>
> *What the sources say*
> • The 2022 UK pilot (61 firms) reported maintained or improved output, and 89%
>   of firms kept the policy [1].
> • A 2023 replication across Ireland/US/Australia found similar results [2].
>
> *Where they disagree*
> • A critique [3] notes both rely on participating firms and self-reported
>   measures, so selection bias likely inflates the result. It doesn't refute the
>   trials but tempers them — and it's the most methodologically careful source.
>
> *Sources*
> [1] 4 Day Week Global UK pilot report — https://… (advocacy org, Feb 2023)
> [2] Boston College trial results — https://… (academic, 2023)
> [3] Economics commentary — https://… (independent critique, 2023)
