---
name: lead-qualification
description: Use when asked to qualify a lead, score a prospect list, or decide whether an inbound inquiry fits the ICP — produces a BANT/MEDDIC score and a go/no-go recommendation.
metadata:
  version: 1.0.0
  display_name: Lead Qualification
  tags: lead qualification, BANT, MEDDIC, scoring, ICP, sales, inbound
---

## Goal

Return a qualification verdict — qualified, nurture, or disqualify — with the evidence behind it so the sales team acts immediately rather than wondering.

## Steps

1. **Establish the scoring criteria** — use the ICP from workspace facts if defined there; otherwise ask. Confirm the qualification framework: BANT (Budget, Authority, Need, Timeline) or MEDDIC (Metrics, Economic Buyer, Decision Criteria, Decision Process, Identify Pain, Champion).
2. **Gather lead data** — accept pasted form data, CRM export, or a list of leads as a table or CSV. For bulk scoring (>5 leads), use `scripts/score_leads.py`.
3. **Score each lead** — apply the criteria from `references/qualification-rubric.md`.
4. **Produce the verdict** for each lead:
   - **Qualified**: score ≥ 70 — hand to AE, include the "why" and suggested opener.
   - **Nurture**: score 40-69 — put in nurture sequence, note what would upgrade them.
   - **Disqualify**: score < 40 — explain why and whether to revisit (e.g., "check back in 6 months if they hit Series B").
5. **Deliver** — for single leads, post verdict + rationale to Slack. For bulk (>5), upload a scored CSV and post a summary table.

## Rules

- A qualification score is a decision input, not the decision. Flag any lead where the score and gut feel diverge, and explain why.
- Never disqualify on company size alone if the stated pain is strong.
- Distinguish "bad fit" (wrong ICP forever) from "bad timing" (right ICP, wrong moment). Handle them differently.
- Use workspace facts for ICP definition, known company exclusions, and target verticals.
