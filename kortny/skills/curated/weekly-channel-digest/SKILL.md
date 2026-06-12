---
name: weekly-channel-digest
description: Use when asked to digest a channel's week, recap what happened in a channel, catch someone up on a channel, or post a recurring "this week in #channel" summary — synthesize the channel's activity into themes, decisions, open questions, and notable links rather than reporting team status.
metadata:
  version: 1.0.0
  display_name: Weekly Channel Digest
  tags: digest, channel, weekly, recap, catch-up, activity
---

## Goal

Synthesize a channel's recent activity into a digest a returning teammate reads in a minute and feels caught up — what the channel was *about* this week, not who did what.

This is a synthesis of channel conversation, not a status report. If the request is "what did the team accomplish / what's our progress," that's `weekly-status-report` (accomplishments grouped by workstream). This skill answers "what happened in here while I was out" — the themes, debates, and decisions that flowed through the channel.

## Steps

1. **Establish the window and channel.** Default to the last 7 days unless the request names a different span ("since Monday", "this month"). State the window in the output. If you can read the channel history, read the whole window before writing; do not summarize from the last few messages.
2. **Pull from Kortny's context, not just raw scroll.** Before synthesizing:
   - Use prior **thread context** and **episodes** if present — a prior digest, a decision recorded earlier, or a summarized thread saves re-reading and keeps wording stable week to week.
   - Use **knowledge-graph context** when present — known projects, owners, and commitments let you attribute a thread to the right initiative instead of guessing.
   - Use **workspace facts** for names, project codenames, and product terms so the digest uses the team's own vocabulary.
3. **Cluster into themes, not into days.** Group the week's messages into 3–6 themes (e.g. "Onboarding redesign", "Q3 pricing debate", "Hiring"). A theme is a thread of conversation, not a single message. Drop one-off chatter that went nowhere.
4. **For each theme, capture:** a one-line summary of where it landed, any **decision** made (with who decided, if stated), and any **open question** still hanging.
5. **Collect notable links** — docs, PRs, dashboards, external articles that were shared and actually discussed. Skip links nobody engaged with.
6. **Surface the open questions in their own section** so the channel can see at a glance what's unresolved.
7. **Close with a single "if you read one thing" pointer** — the one thread that mattered most this week.

## Output shape (Slack mrkdwn)

Post to the channel (or the requesting thread). Lead with a one-line header naming the channel and window. Use this structure, omitting any section that's genuinely empty:

```
*#channel-name — week of Jun 9*

*Themes*
• *Onboarding redesign* — settled on the two-step flow; mockups in the linked doc.
• *Q3 pricing* — still debating per-seat vs. usage. No decision yet.

*Decisions*
• Two-step onboarding flow approved (Dana, Tue).

*Open questions*
• Pricing model — per-seat vs. usage. Owner: Priya, no deadline set.
• Do we need legal review before the launch post?

*Worth a look*
• <link|Onboarding flow doc>
• <link|Pricing comparison sheet>

*If you read one thing:* the pricing thread — it'll affect the launch date.
```

## Rules

- Themes are synthesis. Never paste a transcript or a message dump — if the reader wanted that they'd scroll.
- Decisions name the decider when the channel stated one; otherwise the theme line carries "no decision yet" rather than implying one was made.
- Don't invent owners or deadlines. An open question with no owner says "owner: unclaimed".
- Keep it tight — a typical week is under 250 words. A quiet week is three lines, not padding.
- If a recurring digest, keep theme wording stable week to week so readers can track a thread across digests; a theme that closed this week gets one closing line, then drops next week.
- This can run on a schedule — if asked to "post this every Friday", pair with Kortny's scheduler; the digest body is identical whether triggered by hand or by schedule.

## Worked example

Request in #product on Friday: "give us the weekly digest."

> *#product — week of Jun 9*
>
> *Themes*
> • *Onboarding redesign* — converged on a two-step flow after Dana's mockups landed Tuesday; eng sized it at ~3 days.
> • *Q3 pricing* — long back-and-forth on per-seat vs. usage-based; no resolution, Priya owns the call.
> • *Bug triage* — the export crash (PROD-412) is fixed and shipped.
>
> *Decisions*
> • Two-step onboarding flow approved (Dana, Tue).
>
> *Open questions*
> • Pricing: per-seat vs. usage — owner Priya, no deadline.
>
> *Worth a look*
> • <https://docs.example/onboarding|Onboarding flow doc>
>
> *If you read one thing:* the pricing thread — it gates the Q3 launch date.
