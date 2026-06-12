# build_deck.py spec format

The script accepts a JSON object with an optional `theme` and a list of
`slides`. Pass it via `--spec path.json` or on stdin. Output is a 16:9
widescreen `.pptx`.

## Top level

```json
{ "theme": <theme>, "slides": [ <slide>, ... ] }
```

At least one slide is required. `theme` is optional.

## Theme

| Field      | Type   | Default  | Notes |
|------------|--------|----------|-------|
| `accent`   | string | `2563EB` | Hex (with or without `#`). Used for titles and dividers. |
| `title_pt` | int    | `36`     | Title font size in points. |
| `body_pt`  | int    | `18`     | Body / bullet font size in points. |

## Slides

Every slide has a `layout`. Fields by layout:

### `title` (cover)
| Field      | Type   | Notes |
|------------|--------|-------|
| `title`    | string | Centered accent title. |
| `subtitle` | string | Centered muted subtitle. |

### `section` (divider)
| Field   | Type   | Notes |
|---------|--------|-------|
| `title` | string | Large centered section title. |

### `bullets`
| Field     | Type   | Notes |
|-----------|--------|-------|
| `title`   | string | Slide title (write it as a sentence). |
| `bullets` | array  | Strings. Capped at 6; extras are dropped — split the slide instead. |
| `source`  | string | Optional footer source line. |

### `two_col`
| Field    | Type   | Notes |
|----------|--------|-------|
| `title`  | string | Slide title. |
| `left`   | array  | Left-column bullets (capped at 6). |
| `right`  | array  | Right-column bullets (capped at 6). |
| `source` | string | Optional footer source line. |

### `quote`
| Field         | Type   | Notes |
|---------------|--------|-------|
| `quote`       | string | Centered pull-quote. |
| `attribution` | string | Optional "— name" line. |

## Example

```json
{
  "theme": {"accent": "2563EB", "title_pt": 36, "body_pt": 18},
  "slides": [
    {"layout": "title", "title": "Q1 2026 Review", "subtitle": "Product & Growth"},
    {"layout": "section", "title": "What moved"},
    {"layout": "bullets", "title": "Signups doubled after the referral launch",
     "bullets": ["Signups +112% QoQ", "Activation 41% -> 58%"], "source": "Mixpanel"},
    {"layout": "two_col", "title": "Wins and risks",
     "left": ["Referral loop live"], "right": ["Support backlog growing"]},
    {"layout": "quote", "quote": "The referral link was the biggest lever.",
     "attribution": "Growth team"}
  ]
}
```

Run: `python scripts/build_deck.py --spec spec.json --out deck.pptx`
