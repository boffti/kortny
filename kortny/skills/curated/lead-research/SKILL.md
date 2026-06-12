---
name: lead-research
description: Use when asked to research a lead, look up a company or prospect before a call, qualify an inbound, build a lead sheet, or find out who a person or company is and whether they're a fit — pull from a connected CRM when there is one, fall back to web research, and return a structured, qualified lead sheet.
metadata:
  version: 1.0.0
  display_name: Lead Research
  tags: lead, prospect, research, qualification, crm, company, sales
---

## Goal

Turn a name — a company, a person, or an inbound email — into a structured lead
sheet a rep can act on: who they are, why they might fit, and a qualification
read with the gaps named.

## Steps

1. **Identify the subject and the goal.** Company, person, or both? Pre-call
   prep, inbound triage, or list-building? State what decision the sheet serves
   (e.g. "is this worth a discovery call").
2. **Check for a connected CRM first.** If a Composio CRM/enrichment tool is
   connected — HubSpot, Salesforce, Apollo, and similar — use it before the open
   web: it has the firmographics, prior touches, deal history, and contact
   details already, and it tells you whether this lead is net-new or already in
   the pipeline. Pull existing records and don't duplicate work the CRM has done.
3. **Fall back to web research** when there's no CRM, or to fill gaps the CRM
   doesn't cover. Use **web search** for the company site, recent news, funding,
   headcount, and the person's role/background; pair with the **article-extractor**
   skill to pull clean text from the about/pricing/news pages.
4. **Assemble the lead sheet** with the standard fields in
   `references/lead-sheet.md` — company basics, the contact, fit signals, and
   intent/timing signals. Leave a field blank-but-named ("headcount: unknown")
   rather than guessing it.
5. **Qualify.** Apply the qualification rubric in `references/lead-sheet.md`
   (fit + intent + access) and give a clear read: strong fit / worth a look /
   probably not — with the one or two facts that drove the call.
6. **Name the gaps and the next step.** What's missing to qualify confidently,
   and the single most useful next action (a question to ask, a record to enrich,
   a person to reach).

## Output shape (Slack mrkdwn)

Post a compact sheet to the thread; offer the full version as a canvas or
spreadsheet row if the team tracks leads that way.

```
*Lead: Acme Corp — Jane Doe, VP Eng*

*Company*
• B2B logistics SaaS, ~200 employees, Series B ($30M, 2024).
• Source: <link|site>, <link|funding news>.

*Contact*
• Jane Doe, VP Engineering — owns tooling decisions. <link|LinkedIn>
• In CRM already: one inbound demo request, no owner assigned.

*Fit signals*
• Mid-market, eng-led buyer, growing headcount — matches ICP.
• Stack mentions a competitor we displace.

*Read:* Strong fit — ICP match + active intent (inbound). Worth a discovery call.

*Gaps / next step:* Budget and timeline unknown. Next: book discovery, confirm
who else is on the buying committee.
```

## Rules

- CRM first when one is connected — it's the source of truth for prior contact
  and dedup; researching a lead the team already owns, as if it were net-new,
  wastes everyone's time.
- Never fabricate firmographics, contact details, or funding numbers. Unknown is
  a valid field value and far more useful than a confident guess.
- Cite where each fact came from (CRM record vs which web source) so the rep can
  verify and so stale data is obvious.
- Respect the obvious line on personal data — research public professional
  information (role, company, public posts), not private personal details.
- The qualification read is a recommendation, not a verdict; state the facts that
  drove it so the rep can disagree with their own context.
- Flag stale data — a "2021 funding" line on a 2026 lead needs a freshness check.

## Worked example

Inbound triage, HubSpot connected: "research this inbound — jane@acme.com."

> *Lead: Acme Corp — Jane Doe, VP Eng*
>
> *Company*
> • Logistics SaaS, ~200 staff, Series B ($30M, 2024). Sources: <site>, <funding>.
>
> *Contact*
> • Jane Doe, VP Engineering. Already in HubSpot — submitted the pricing form
>   yesterday, unassigned, no prior deals.
>
> *Fit signals*
> • Mid-market eng-led buyer, headcount up 30% YoY — clean ICP match.
> • Public job posts mention a competitor we replace.
>
> *Read:* Strong — ICP fit plus fresh inbound intent. Route to AE today.
>
> *Gaps / next step:* No budget/timeline yet, buying committee unknown. Next:
> assign an owner in HubSpot and book discovery this week.
