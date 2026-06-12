# 3P Updates (Progress · Plans · Problems)

Vendored from anthropics/skills@57546260 under Apache-2.0, adapted for Slack delivery.

---

## Purpose

3P updates stand for "Progress, Plans, Problems." The audience is leadership, other teams, or anyone who needs a fast situational read. They are designed to be readable in 30–60 seconds by someone with moderate context on the team.

3Ps can cover a team of any size. The bigger the scope, the less granular each point should be: a product squad might say "shipped auto-retry for failed jobs"; the whole company might say "closed 10 new enterprise deals."

---

## Sections

**Progress** — what the team accomplished in the covered period. Focus on things shipped, milestones reached, tasks closed.

**Plans** — what the team intends to do in the next period. Focus on the highest-priority items, not an exhaustive list.

**Problems** — anything slowing the team down. Blockers, under-resourcing, a deal that fell through, a bug preventing a launch.

---

## Information gathering

Use known workspace tools and connected data sources when available:
- Recent Slack messages from team members in public channels (high-reaction posts are signal-rich)
- Linked documents or shared notes from the covered period
- Calendar entries — especially non-recurring meetings like reviews or decision sessions

If tools are unavailable, ask the user directly what they want to cover. They may supply the content and just need formatting help.

---

## Formatting (strict — do not deviate)

```
[emoji] [Team Name] ([Date range, e.g. Jun 9–13])
Progress: [1–3 sentences]
Plans: [1–3 sentences]
Problems: [1–3 sentences]
```

Pick an emoji that captures the team's vibe or the week's theme. Each section is a maximum of 1–3 sentences: clear, direct, data-driven. Include metrics where they exist. Tone: matter-of-fact, not prose-heavy.

---

## Scope calibration

| Team scope | Appropriate granularity |
|---|---|
| Small squad (3–8 people) | Individual features shipped, specific bugs fixed |
| Department (20–80 people) | Product area milestones, hiring numbers, revenue targets |
| Company-wide | Major launches, key deals, executive changes, macro metrics |

Before writing, confirm: team name, time period (usually the past week for Progress/Problems, next week for Plans).

---

## Workflow

1. Clarify team name and date range if not supplied
2. Gather context from available tools or ask the user
3. Draft against the strict format above
4. Review: does it read in under 60 seconds? Is it data-driven? If not, cut.
5. Post to the appropriate Slack channel — or offer to pair with a recurring schedule if this update happens weekly
