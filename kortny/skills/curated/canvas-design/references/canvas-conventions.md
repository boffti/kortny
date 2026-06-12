# Slack canvas markdown conventions

Slack canvases support a subset of markdown. This reference lists what is and is not available.

## Supported elements

| Element | Syntax | Notes |
|---|---|---|
| Heading 1 | `# Heading` | Use for canvas title only |
| Heading 2 | `## Section` | Main sections |
| Heading 3 | `### Sub-section` | Subsections within a section |
| Bold | `**text**` | Inline emphasis for key terms |
| Italic | `_text_` | Sparingly; for titles or terms |
| Bullet list | `- item` | Unordered; preferred for reference lists |
| Numbered list | `1. item` | For sequential steps only |
| Code block | ` ``` code ``` ` | For commands, values, config snippets |
| Inline code | `` `value` `` | For field names, file paths, exact strings |
| Horizontal rule | `---` | Between major sections; use sparingly |
| Link | `[text](url)` | External references; label the link meaningfully |

## Not supported in canvases

- Tables (not rendered in Slack canvas)
- HTML tags
- Embedded images (can be attached, not inline)
- Blockquotes (`>`) — avoid; renders inconsistently

## Canvas structure conventions

### Standard sections

For most canvas types, use this top-level structure:

```
# [Title]

_Last updated: [date] | Owner: [name or team]_

---

## Purpose

One sentence stating why this canvas exists and who it's for.

## [Main content sections]

...

## Open questions

Unresolved items with owners.

## Change log

| Date | Change | Author |
```

### Reference docs

Add a "How to use this document" note at the top if the canvas is long or has non-obvious navigation.

### Decision records

Mandatory sections: Context → Options considered → Decision → Rationale → Consequences.

## Design notes

- Use `---` horizontal rules to separate major sections (not between every heading).
- Limit nesting to 2 levels of bullets. Deeper nesting is a sign the content needs restructuring.
- Every `[FILL: …]` placeholder must be on its own line so it's easy to spot and replace.
