# Provenance

Independently authored for Kortny (2026-06-12). Concept and capability slot informed by research into https://github.com/TerminalSkills/skills (Apache-2.0); no upstream text or files were copied.

## Design notes

- `scripts/score_leads.py` included per HIG-239 instruction; written using stdlib `csv` only — no pandas dependency needed for pure CSV scoring, avoids a heavyweight dep for a simple transform.
- Output targets single-lead verdict in Slack post, bulk scored CSV upload rather than local files.
- Scoring rubric uses BANT framework with MEDDIC reference.
- `scripts/score_leads.py`: argparse CLI, stdlib only (csv module), no network access.
