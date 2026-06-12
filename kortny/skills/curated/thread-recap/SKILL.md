---
name: thread-recap
description: Use when asked to recap this thread, summarize the discussion above, TL;DR a long thread, or pull the decisions and action items out of the conversation right here — work from the live Slack thread in front of you and post a tight recap back into it.
metadata:
  version: 1.0.0
  display_name: Thread Recap
  tags: recap, thread, tldr, decisions, action-items, summary
---

## Goal

Turn the Slack thread the request is happening *in* into a recap that lets a latecomer act without scrolling — decisions, action items with owners, and open questions.

This works from the **live thread** — the messages already in the conversation Kortny is part of. It's not the same as `meeting-notes-summarizer`, which takes a pasted transcript, uploaded notes, or call recording as its source. If the user attaches a transcript or paste, that's meeting-notes-summarizer. If they say "recap this" / "TL;DR the thread above", that's this skill: the thread *is* the input.

## Steps

1. **Read the whole thread before writing.** Kortny already has the thread context assembled — use it. Read from the first message, not just the recent replies, so you don't miss a decision that was later assumed-settled.
2. **Use workspace facts and graph context** for names and project terms — refer to people and projects the way the team does, and don't invent display names from user IDs.
3. **Extract in this order:**
   - **Decisions** — what was agreed, and who agreed it (name the person only if the thread shows it).
   - **Action items** — task → owner → due date if stated. An item with no clear owner is flagged `(unassigned)`; never assign one by guessing.
   - **Open questions** — anything raised and left hanging.
   - **Key context** — at most 2–3 lines that explain *why* the decisions landed where they did, for someone who wasn't here.
4. **Distinguish settled from still-debated.** If two people disagreed and nobody closed it, that's an open question, not a decision.
5. **Post the recap back into the same thread** so it lives where the discussion happened.

## Output shape (Slack mrkdwn)

Lead with a one-line TL;DR, then the sections below, omitting any that are empty. Keep it well under the length of the thread itself.

```
*TL;DR:* Agreed to ship the two-step onboarding flow next sprint; pricing still open.

*Decisions*
• Two-step onboarding flow approved — Dana.

*Action items*
• Wire the second step — Sam, by Thu.
• Update the help doc — (unassigned).

*Open questions*
• Per-seat vs. usage pricing — nobody owns this yet.

*Context*
• Single-step flow was dropping ~30% at the email step; the second step fixes verification.
```

## Rules

- Only what's in the thread. No outside facts, no inferred owners, no invented dates.
- Action items are imperative and assignable: "Wire the second step — Sam, Thu", not "the second step should probably get built".
- If the thread is still actively going (the request came mid-discussion), say so: "Recap as of now — thread still live." so nobody treats it as final.
- One TL;DR line, not a paragraph. If you can't say the gist in a sentence, the thread hasn't actually concluded — recap the state and the open questions.
- Don't recap a thread that's three messages long; just answer the question. This skill earns its keep on long threads.

## Worked example

Mid-thread request: "@kortny can you recap this?"

> *TL;DR:* Settled on the two-step onboarding flow for next sprint; pricing model still undecided.
>
> *Decisions*
> • Two-step onboarding flow approved — Dana.
>
> *Action items*
> • Build the verification step — Sam, by Thursday.
> • Refresh the onboarding help doc — (unassigned).
>
> *Open questions*
> • Pricing: per-seat vs. usage — raised by Priya, no owner yet.
>
> *Context*
> • The single-step flow was losing ~30% of signups at email verification; the added step is meant to recover that.
>
> _Recap as of now — thread still live._
