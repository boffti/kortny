# make_chart.py spec format

The script accepts a JSON object describing one chart. Pass it via
`--spec path.json` or on stdin. Output is a PNG.

## Fields

| Field     | Type   | Notes |
|-----------|--------|-------|
| `type`    | string | `bar` (default), `hbar`, `line`, or `pie`. |
| `title`   | string | Write it as the takeaway, not the metric name. |
| `x_label` | string | X-axis label with units. Ignored for `pie`. |
| `y_label` | string | Y-axis label with units. Ignored for `pie`. |
| `labels`  | array  | Category labels (x positions / pie slices). |
| `series`  | array  | List of `{name, values}`. `bar`/`line` support multiple; `hbar`/`pie` use the first. |
| `source`  | string | Optional source caption, bottom-left. |

## Chart types

- **`bar`** — vertical bars. Multiple series render grouped side by side and
  add a legend.
- **`hbar`** — single-series horizontal bars; use when category labels are
  long. First category appears on top.
- **`line`** — one line per series with markers; multiple series add a legend.
- **`pie`** — single series, **maximum 5 slices**. The script raises an error
  for more than 5 — use a bar chart instead. Only produce a pie on explicit
  request.

## Conventions baked into the output

- Colorblind-friendly palette (Okabe-Ito subset).
- Grid on the value axis only; top and right spines removed.
- Thousands separators on numeric ticks.
- 144 DPI, ~9×5.2 inch figure, tight layout.

## Examples

Grouped bar:

```json
{
  "type": "bar",
  "title": "Signups doubled after the referral launch",
  "x_label": "Week", "y_label": "Signups",
  "labels": ["W1", "W2", "W3", "W4"],
  "series": [
    {"name": "Signups", "values": [1200, 1800, 2400, 3600]},
    {"name": "Activations", "values": [500, 900, 1400, 2100]}
  ],
  "source": "Mixpanel, Apr 2026"
}
```

Line:

```json
{
  "type": "line",
  "title": "p95 latency is trending down",
  "x_label": "Day", "y_label": "ms",
  "labels": ["Mon", "Tue", "Wed"],
  "series": [{"name": "p95", "values": [210, 180, 160]}]
}
```

Run: `python scripts/make_chart.py --spec spec.json --out chart.png`
