#!/usr/bin/env python3
"""
score_leads.py — Bulk lead qualification scorer.

Reads a CSV of leads, applies BANT scoring heuristics,
and outputs a scored CSV with qualification tier.

Usage:
    python score_leads.py --input leads.csv --output scored_leads.csv

Input CSV expected columns (case-insensitive, extras ignored):
    company, contact_name, contact_title, industry, company_size,
    budget_signal, timeline, pain_description, notes

Output adds columns: bant_score, qualification_tier, reason

Runs inside the Kortny sandbox (trusted tier only).
No network access required.
"""

import argparse
import csv
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _score_authority(title: str) -> int:
    """Score based on contact title keywords."""
    t = title.lower()
    if any(k in t for k in ("ceo", "cto", "cfo", "coo", "founder", "president", "owner")):
        return 25
    if any(k in t for k in ("vp", "vice president", "director", "head of")):
        return 18
    if any(k in t for k in ("manager", "lead", "principal")):
        return 10
    return 3


def _score_budget(budget_signal: str) -> int:
    """Score based on free-text budget signal."""
    b = budget_signal.lower()
    if any(k in b for k in ("confirmed", "allocated", "approved", "budget in place")):
        return 25
    if any(k in b for k in ("likely", "series b", "series c", "growth stage", "enterprise")):
        return 15
    if any(k in b for k in ("unclear", "unknown", "tbd", "exploring")):
        return 5
    if any(k in b for k in ("no budget", "no spend", "no money", "free only")):
        return 0
    return 5  # Default: unclear


def _score_need(pain: str) -> int:
    """Score based on pain description length and specificity heuristic."""
    p = pain.strip()
    if len(p) == 0:
        return 0
    # Heuristic: longer, specific descriptions score higher
    word_count = len(p.split())
    if word_count >= 20:
        return 30
    if word_count >= 10:
        return 18
    if word_count >= 3:
        return 8
    return 4


def _score_timeline(timeline: str) -> int:
    """Score based on timeline text."""
    t = timeline.lower()
    if any(k in t for k in ("immediate", "asap", "this month", "this quarter", "30 days", "<30")):
        return 20
    if any(k in t for k in ("next quarter", "60 days", "90 days", "3 months", "q1", "q2", "q3", "q4")):
        return 14
    if any(k in t for k in ("6 months", "h2", "next year", "exploring", "looking")):
        return 7
    return 3  # Default: no timeline


def _tier(score: int) -> str:
    if score >= 70:
        return "Qualified"
    if score >= 40:
        return "Nurture"
    return "Disqualify"


def _reason(score: int, authority: int, need: int, budget: int, timeline: int) -> str:
    parts = []
    if need == 0:
        parts.append("no pain stated")
    if authority <= 3:
        parts.append("IC-level contact")
    if budget == 0:
        parts.append("no budget")
    if timeline <= 3:
        parts.append("no timeline")
    if score >= 70:
        parts.append("meets qualification threshold")
    elif score >= 40:
        parts.append("partial fit — nurture until " + (
            "budget clears" if budget < 15 else
            "need sharpens" if need < 15 else
            "timeline firms up"
        ))
    else:
        parts.append("does not meet qualification threshold")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def score_row(row: dict[str, str]) -> dict[str, str]:
    keys = {k.lower().strip(): v for k, v in row.items()}
    authority = _score_authority(keys.get("contact_title", ""))
    budget = _score_budget(keys.get("budget_signal", ""))
    need = _score_need(keys.get("pain_description", ""))
    timeline = _score_timeline(keys.get("timeline", ""))
    total = authority + budget + need + timeline
    tier = _tier(total)
    reason = _reason(total, authority, need, budget, timeline)
    return {
        **row,
        "bant_score": str(total),
        "qualification_tier": tier,
        "reason": reason,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk BANT lead scorer")
    parser.add_argument("--input", required=True, help="Input CSV path")
    parser.add_argument("--output", required=True, help="Output CSV path")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with input_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("Error: empty or malformed CSV", file=sys.stderr)
            sys.exit(1)
        rows = [score_row(dict(row)) for row in reader]
        out_fields = list(reader.fieldnames) + ["bant_score", "qualification_tier", "reason"]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rows)

    qualified = sum(1 for r in rows if r["qualification_tier"] == "Qualified")
    nurture = sum(1 for r in rows if r["qualification_tier"] == "Nurture")
    disqualify = sum(1 for r in rows if r["qualification_tier"] == "Disqualify")
    print(f"Scored {len(rows)} leads: {qualified} Qualified, {nurture} Nurture, {disqualify} Disqualify")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
