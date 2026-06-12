# SKILL.md frontmatter specification

Every curated or custom skill must begin with a YAML frontmatter block delimited by `---`.

## Required fields

```yaml
---
name: slug-kebab-case
description: "Use when …"
metadata:
  version: 1.0.0
  display_name: Human Readable Name
---
```

### `name`

- Kebab-case slug, lowercase, ASCII only.
- Must be globally unique within the skill registry.
- Used as the directory name and the DB slug.
- Examples: `competitive-analysis`, `brand-template`, `skill-creator`.

### `description`

- **Selection-first**: written from the user's perspective. Start with "Use when…" or similar trigger phrasing.
- The embedding model ingests this field — write the phrases users would naturally type.
- Single sentence, under 200 characters.
- Do NOT describe the skill's mechanism; describe the trigger scenario.

  Good: `"Use when asked to compare competitors or assess how a product stacks up against alternatives."`
  Bad: `"A skill that performs competitive analysis using web search and a structured framework."`

### `metadata.version`

- Semantic version string (`major.minor.patch`). Start at `1.0.0`.
- Bump patch for content fixes, minor for new sections/references, major for structural rewrites.

### `metadata.display_name`

- Title-case, human-readable name shown in the dashboard.
- 2-5 words. No punctuation.

## Optional fields

```yaml
metadata:
  tags: comma, separated, trigger, keywords
  trust_tier: trusted      # trusted | community | untrusted (default: trusted for curated)
  default_enabled: false   # true = auto-enabled at workspace scope on seeding
```

### `metadata.tags`

- Comma-separated list of keywords, lowercase.
- Used for lexical fallback matching when embeddings are unavailable.
- Include synonyms, trigger phrases, and task nouns.

### `metadata.trust_tier`

- Curated skills default to `trusted` (required for script execution).
- Custom ingested skills default to `untrusted`.

### `metadata.default_enabled`

- `true` = the skill is auto-enabled at workspace scope when seeded.
- Reserved for the default pack list in `service.py`. Do not set this manually unless coordinating with the platform team.

## Body structure

After the frontmatter, the body must contain:

1. `## Goal` — one sentence.
2. `## Steps` — numbered, imperative.
3. `## Rules` — non-negotiable constraints. Keep under 6 bullets.

Optional sections: `## Output`, `## Output shape`, `## Script specs`.

Total SKILL.md length: under 600 words. If you need more, move content into `references/*.md`.
