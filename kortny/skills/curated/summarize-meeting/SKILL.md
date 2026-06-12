---
name: summarize-meeting
description: Use when asked to process a meeting transcript file or uploaded recording summary and produce a structured PM artifact — decision log, action items with owners and due dates, blockers, and next-meeting agenda seed. Pairs with project management tools (Jira, Linear, Notion via Composio) to push action items directly.
metadata:
  version: 1.0.0
  display_name: Summarize Meeting
  tags: meeting, transcript, action items, PM, project management, decisions, blockers
---

## Goal

Turn a meeting transcript or uploaded notes into a structured, actionable PM artifact that feeds directly into how your team tracks work — not just a summary to read.

## How this differs from meeting-notes-summarizer

`meeting-notes-summarizer` is a general-purpose skill for converting any notes or transcripts into a clean summary.

`summarize-meeting` goes further: it produces a **structured PM artifact** with required fields (decision log with rationale, action items with explicit owners and due dates, blockers with names), and can push action items directly to connected project management tools via Composio (Jira, Linear, Notion, Asana). Use this when the output needs to live in your PM tool, not just in a Slack thread.

## Steps

1. **Accept the input** — transcript file, uploaded recording summary, or pasted text. If multiple documents, process them in order.
2. **Identify the meeting context** — project name, date, participants (from the transcript; do not invent names or roles).
3. **Extract with PM rigor** — for each item, require owner + due date or flag as incomplete:
   - **Decisions** (what was decided, by whom, and the key rationale — not just "decided to proceed").
   - **Action items** (task, owner, due date — flag `[no owner]` and `[no due date]` explicitly).
   - **Blockers** (what's blocking, who owns the unblock, and what unblocks it).
   - **Deferred items** (what was explicitly pushed to later — helps avoid re-discussion).
4. **Produce the PM artifact** — use the format in `references/meeting-artifact-template.md`.
5. **Push to PM tool** — if a connected PM tool is available via Composio (Jira, Linear, Notion, Asana), offer to create action items as tasks. Ask before doing so.
6. **Post to Slack** — post the structured summary to the thread; offer the next-meeting agenda seed based on open items.

## Rules

- Never invent owners or due dates. Unassigned items must be flagged, not guessed.
- Decisions need rationale captured — "decided to use Postgres" without the "because" loses the institutional memory.
- The next-meeting agenda seed comes only from open items, not invented topics.
- If the transcript is partial or cut off, say so at the top.
