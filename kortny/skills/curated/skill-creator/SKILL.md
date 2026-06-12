---
name: skill-creator
description: Use when asked to create a new Kortny skill, write a SKILL.md for a custom capability, or package a repeatable workflow as a skill that can be enabled for a workspace, channel, or user.
metadata:
  version: 1.0.0
  display_name: Skill Creator
  tags: skill, skill-creator, admin, meta, custom, package, workflow, automation
---

## Goal

Produce a complete, ingestion-ready skill directory that passes curated-skill quality bars — selection-first description, clear steps, tight rules.

## Steps

1. **Gather the skill brief**: what task does this skill handle, who triggers it, what does the output look like? If the request is vague, ask: (a) what's the trigger phrase a user would type? (b) what format is the output?
2. **Draft the frontmatter** following this exact schema (see `references/frontmatter-spec.md`):
   ```yaml
   name: slug-kebab-case
   description: "Use when …" — one sentence, written from the user's perspective.
   metadata:
     version: 1.0.0
     display_name: Human Readable Name
     tags: comma, separated, trigger, words
   ```
3. **Write the body**: Goal section (one sentence), Steps (numbered, imperative), Rules (non-negotiable constraints). Keep total SKILL.md under 600 words.
4. **Add references/** only if the skill genuinely needs referenceable lookup material (dimension lists, templates, checklists). Each references/*.md should be a named lookup, not more instructions.
5. **Add scripts/** only if a computation or file transformation is needed that cannot be done in prose instructions. Python, stdlib plus the sandbox image deps. Each script: argparse, file-in/file-out, no network calls.
6. **Verify the description is selection-first**: paste it back and ask — "if a user typed this in Slack, would this skill obviously be the right one?" If not, rewrite the description before finalising.

## Output

Emit the full directory structure as code blocks in a single Slack message:
- `SKILL.md` — complete content
- `references/` files if any — complete content
- `scripts/` files if any — complete content

Offer to upload the directory as a zip for dashboard ingestion, or instruct the admin to paste the SKILL.md via the dashboard skill editor.

## Rules

- The `name` field must be unique within the curated pack; suggest a slug and warn if it might conflict.
- Never write a skill whose description overlaps substantially with an existing skill — check the enabled skill list first.
- Scripts only run at `trusted` tier; flag if the requester's workspace is not at that trust level.
- Do not include the skill's own creation instructions inside the new skill — that is circular.
