---
name: prospecting
description: Use when asked to find potential leads, build a prospect list, identify target accounts, or research companies that fit a specific buyer profile.
metadata:
  version: 1.0.0
  display_name: Prospecting
  tags: prospecting, leads, sales, ICP, target accounts, outbound
---

## Goal

Build a qualified prospect list — companies or individuals who fit the ICP and have buying signals — ready for outreach.

## Steps

1. **Confirm the ICP** — industry vertical, company size (headcount or ARR band), geography, tech stack signals, and any exclusions. Use workspace facts from Kortny's knowledge graph if the ICP is already defined there.
2. **Identify buying signals** — what triggers a purchase? (headcount growth, new funding, new hire in the buyer role, product launch, job postings for tools you replace.) Prioritize prospects showing at least one signal.
3. **Research via available tools** — use web search, connected CRM tools (HubSpot, Salesforce, Apollo via Composio if available), and LinkedIn signals from job postings. Document each source.
4. **Score each prospect** — use the scoring rubric in `references/scoring-rubric.md`. Record fit score and signal strength.
5. **Deliver the list** — post a table to Slack (company, role/contact, fit score, top signal, suggested opener angle). For lists over 10 accounts, upload as a file.
6. **Suggest next step** — for the top 3 accounts, draft a one-line opener angle that ties to their specific signal.

## Rules

- Only use publicly available information. No scraping gated data or guessing personal contact details.
- Prospect lists go stale fast — timestamp the list and note the signal date for each entry.
- Do not include prospects if you cannot identify at least one genuine buying signal.
- Use workspace facts about your product's positioning when writing opener angles.
