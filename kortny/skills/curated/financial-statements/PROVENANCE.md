# Provenance

**Concept source**: anthropics/claude-cookbooks (analyzing-financial-statements notebook)
**Source repo**: https://github.com/anthropics/claude-cookbooks
**License**: MIT
**Commit reference**: HEAD as of 2026-06-12 (concept-level reference; no code copied)
**Slug in plan**: `financial-statements` (from cookbooks' analyzing-financial-statements)
**Adaptation date**: 2026-06-12
**Adapted by**: Agent A (HIG-239)

## What was adapted

The SKILL.md and reference file are original clean-room authorships inspired by the claude-cookbooks analyzing-financial-statements notebook. The cookbook illustrates financial ratio analysis using Claude; this skill adapts that scope into a Kortny procedural skill with Slack-first output.

No notebook cells, code, or prose were copied from the upstream source.

## Key adaptations from upstream

- No Jupyter notebook format; skill is prose instructions + reference table.
- Output is Slack-formatted: ratio table + plain-language paragraph, not a Python data-science output.
- Reference file (`references/key-metrics.md`) is original; the metric set draws from standard financial analysis conventions (public domain), not from the cookbook's specific content.
- Anomaly/flag handling made explicit (restatements, SBC add-backs, lease treatment).

## License

MIT License — anthropics/claude-cookbooks (concept reference only; no copied text or code).
