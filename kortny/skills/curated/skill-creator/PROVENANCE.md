# Provenance

**Concept source**: anthropics/skills (skill-creator / meta-skill concept)
**Adaptation date**: 2026-06-12
**Adapted by**: Agent A (HIG-239)

## What was adapted

This skill was written fresh — no text was copied from the upstream source. The concept of a meta-skill that helps users and admins create new skills is inspired by the anthropics/skills skill-creator pattern, but all prose, steps, rules, and the frontmatter specification reference were authored independently.

Reason for fresh authoring: the upstream source is proprietary (anthropics internal). Conservative approach is to write from scratch.

## Kortny-specific adaptations

- Output delivery options: emit as Slack code blocks, or upload as zip for dashboard ingestion.
- References Kortny's trust-tier system (trusted/community/untrusted/quarantined).
- References Kortny's skill scoping (workspace/channel/user enablement).
- Frontmatter spec matches Kortny's ingestion format exactly (not claude.ai/code's format).
- No `.claude/` paths; no reference to Claude Code CLI conventions.

## License

Original concept source is proprietary — this skill is a clean-room rewrite.
This file and all files in this directory are subject to the Kortny project license.
