---
name: release-notes
description: Use when asked to write release notes, a changelog entry, or a "what's new" announcement for a product release — audience-appropriate language, benefit-led, with upgrade guidance where relevant.
metadata:
  version: 1.0.0
  display_name: Release Notes
  tags: release notes, changelog, what's new, product update, announcement
---

## Goal

Write release notes that customers actually read — benefit-led, scannable, honest about what changed and why it matters.

## Steps

1. **Gather the release content** — accept a list of PRs, a ticket list, a diff summary, or a free-form description of what shipped. Group by type: new features, improvements, bug fixes, deprecations, breaking changes.
2. **Clarify the audience** — technical users (developers, admins) read differently than end users. Confirm which.
3. **Rewrite for the audience** — convert ticket-speak to customer-speak. "Fixed null pointer on export" → "Exports no longer fail when a row has an empty date field."
4. **Apply the structure** from `references/release-notes-structure.md`. Lead with the highest-value change, not the easiest to write.
5. **Flag breaking changes prominently** — at the top, with migration steps if relevant.
6. **Deliver** — post to Slack in the #releases or relevant channel; offer to post as a canvas for longer notes.

## Rules

- Lead with the benefit, not the implementation: "You can now export to PDF" not "Added PDF export handler".
- Every breaking change gets its own section at the top with a migration path or link to docs.
- Bug fixes can be grouped; don't inflate a release with a list of 20 minor fixes when "several stability improvements" is more honest.
- Omit internal-only changes (refactors, test additions, CI fixes) unless the audience is developers reading a technical changelog.
- If a feature is in beta or limited availability, say so clearly.
- Use workspace facts for product name, version numbering conventions, and brand voice if defined.
