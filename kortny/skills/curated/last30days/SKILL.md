---
name: last30days
description: Use when asked for a "last 30 days" summary or retrospective of a topic, company, market, or person — systematically research what happened, what changed, and what it means, using web search and any available context.
metadata:
  version: 1.0.0
  display_name: Last 30 Days
  tags: research, retrospective, 30 days, what happened, timeline, news, summary
---

## Goal

Produce a crisp, factual "what happened in the last 30 days" briefing on any subject — news, company, market, person, or project — that surfaces what changed and why it matters.

## When to use

Use when someone asks "what's been happening with X lately?", "catch me up on [company]", "what changed in [market] this month?", or any variant that implies a recent-events research task.

## Steps

1. **Confirm the subject and period** — what exactly to research; confirm "last 30 days" vs. a specific date range.
2. **Research via available tools** — use web search (Brave search if enabled, otherwise web_search tool) to find recent coverage. Search multiple angles:
   - "[Subject] news" last 30 days
   - "[Subject] announcement" OR "[Subject] release" for the period
   - "[Subject] funding" / "[Subject] launch" / "[Subject] controversy" as relevant
   - Verify: only include items dated within the stated period. Discard older results.
3. **Structure the findings** — use `references/last30days-methodology.md` for the briefing structure. Group by: key events (timeline), significant changes, what's stayed the same, and what's uncertain.
4. **Write the verdict** — 1-sentence "so what": what does the last 30 days tell us about where this subject is heading?
5. **Deliver** — post the briefing to Slack inline if under 300 words; as a canvas if longer.

## Rules

- Only include verifiable, dated events. State the date for each item.
- If web search is unavailable, say so and offer to work with whatever context was shared in the thread.
- No fabricated events. If a search returns no recent news, say "no significant developments found in this period."
- The "so what" must go beyond summarizing — it should draw an implication or highlight a trend.
- Do not require any specific API key. This skill works with any available web search capability.
