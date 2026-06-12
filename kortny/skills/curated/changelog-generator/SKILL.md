---
name: changelog-generator
description: Use when asked to generate a changelog from a list of commits, PRs, or tickets — categorizes changes, strips noise, and produces a clean human-readable changelog in Keep a Changelog format or a custom format.
metadata:
  version: 1.0.0
  display_name: Changelog Generator
  tags: changelog, commits, release, git log, version history, PR summary
---

## Goal

Turn a raw list of commits, PR titles, or Jira/Linear tickets into a clean, human-readable changelog that developers and users can actually navigate.

## Steps

1. **Accept the input** — paste commit messages, PR titles, ticket summaries, or a raw `git log` output. If the period is ambiguous, confirm the date range or version range.
2. **Categorize each change** — use Keep a Changelog categories: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. Assign each input item to one category.
3. **Strip noise** — discard: merge commits, CI/tooling-only changes (unless internal audience), version bumps, typo fixes unless they fix user-visible content, `chore:` and `refactor:` commits without user impact.
4. **Rewrite for humans** — convert commit shorthand to plain English. "feat(auth): add PKCE flow" → "Added PKCE support for OAuth flows (improves security for public clients)."
5. **Apply the format** from `references/changelog-format.md` — or follow the user's existing format if provided.
6. **Deliver** — post to Slack in the relevant channel; offer as a canvas or file for longer changelogs.

## Rules

- Lead with the highest-impact change in each category, not the first commit alphabetically.
- Breaking changes always get a dedicated `⚠ Breaking` section above all others.
- Do not include security vulnerability details in the public changelog — link to the advisory instead.
- If the input contains duplicate or near-duplicate entries (squash merges), merge them into one line.
- Use workspace facts for product name and version numbering conventions.
