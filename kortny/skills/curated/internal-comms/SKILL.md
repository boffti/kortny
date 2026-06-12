---
name: internal-comms
description: Use when asked to draft an internal company announcement, all-hands update, leadership message, policy change notice, or org-wide memo for posting to Slack or a canvas.
metadata:
  version: 1.0.0
  display_name: Internal Communications
  tags: announcement, all-hands, memo, comms, internal, leadership, policy, update
---

## Goal

Draft a clear, appropriately toned internal message that leadership would be comfortable sending — no filler, no corporate fog.

## Steps

1. Clarify the audience and channel before drafting: all-company, a team, a specific group. If unclear, ask one question.
2. Identify the message type and set tone accordingly:
   - **Announcement** (new policy, org change, hire) — factual, forward-looking, brief.
   - **Update** (project progress, initiative recap) — structured by workstream; use known workspace facts about the product/brand if present.
   - **Sensitive message** (layoffs, leadership change, incident) — plain language, no spin; acknowledge impact first.
3. Draft the message:
   - Lead with the one-sentence headline — what is changing or happening.
   - Body: context (why), what it means for the reader, what action (if any) they should take, and timeline.
   - Close with a clear next step or contact point.
4. Check tone: would a thoughtful colleague consider this honest and respectful? If not, revise.
5. Offer the Slack-post version (mrkdwn, ~150 words) and — if the content warrants it — a canvas version for reference material.

## Output shapes

- **Slack post**: mrkdwn, scannable bullets, under 200 words for most announcements.
- **Canvas**: used for policy docs, FAQs, or anything employees will return to. Offer this when the content has a reference shelf-life.
- **Scheduler pairing**: if this message recurs (weekly team update, monthly all-hands prep), note "this can be paired with a schedule — ask me to set a recurring reminder."

## Format-specific guides

Load the appropriate reference file for the requested communication type:

| Format | Reference | Use when |
|---|---|---|
| 3P update | `references/3p-updates.md` | Progress/Plans/Problems team update for leadership |
| Company newsletter | `references/company-newsletter.md` | Weekly or monthly company-wide digest |
| FAQ answers | `references/faq-answers.md` | Answering recurring employee questions |
| General / other | `references/general-comms.md` | Policy changes, incident updates, milestone posts, or anything that doesn't fit the above |

If the request clearly maps to one of these formats, load the reference immediately and follow its formatting rules. If it's ambiguous, ask one clarifying question about the audience and purpose, then load the best-fit reference.

## Rules

- No filler openings ("I'm excited to share…", "As we continue our journey…").
- Blockers or risks get named, not softened into vague "challenges".
- Never fabricate org details, names, or dates. Use known workspace facts if present; otherwise leave a `[PLACEHOLDER]` for the sender to fill.
- One message per draft. If two distinct audiences need different messages, produce two and say so.
