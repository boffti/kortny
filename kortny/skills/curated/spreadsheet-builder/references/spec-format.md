# build_workbook.py spec format

The script accepts a JSON object describing one or more sheets. Pass it via
`--spec path.json` or on stdin.

## Top level

```json
{ "sheets": [ <sheet>, ... ] }
```

At least one sheet is required.

## Sheet

| Field             | Type   | Notes |
|-------------------|--------|-------|
| `name`            | string | Sheet tab name (truncated to 31 chars). |
| `columns`         | array  | Data columns, in order. See below. Required. |
| `rows`            | array  | Row objects keyed by each column's `key`. |
| `formula_columns` | array  | Computed columns appended after the data columns. |
| `total_row`       | bool   | When true, appends a `SUM` total row over numeric columns. |

## Column

| Field    | Type   | Notes |
|----------|--------|-------|
| `header` | string | Column header text (row 1). |
| `key`    | string | Key used to read the value from each row object. |
| `format` | string | One of `currency`, `currency_whole`, `percent`, `thousands`, `number`, `date`, `text`. |
| `signed` | bool   | When true, numeric values render green if ≥ 0, red if < 0. |

## Formula column

| Field     | Type   | Notes |
|-----------|--------|-------|
| `header`  | string | Header text. |
| `formula` | string | Excel formula template. Use `{key}` for a data column's letter and `{row}` for the current row number, e.g. `={qty}{row}*{price}{row}`. |
| `format`  | string | Same format names as a data column. |

## Number format strings

The friendly names map to these Excel format codes (negatives render red):

| Name             | Excel code |
|------------------|------------|
| `currency`       | `#,##0.00;[Red]-#,##0.00` |
| `currency_whole` | `#,##0;[Red]-#,##0` |
| `percent`        | `0.0%;[Red]-0.0%` (store rates as fractions, e.g. `0.12`) |
| `thousands`      | `#,##0;[Red]-#,##0` |
| `number`         | `0.00;[Red]-0.00` |
| `date`           | `yyyy-mm-dd` |
| `text`           | `@` |

## Example

```json
{
  "sheets": [
    {
      "name": "Q1 Forecast",
      "columns": [
        {"header": "Region", "key": "region", "format": "text"},
        {"header": "Revenue", "key": "rev", "format": "currency", "signed": true},
        {"header": "Units", "key": "units", "format": "thousands"},
        {"header": "Growth", "key": "growth", "format": "percent", "signed": true}
      ],
      "rows": [
        {"region": "EMEA", "rev": 120000, "units": 3400, "growth": 0.12},
        {"region": "APAC", "rev": -5000, "units": 800, "growth": -0.03}
      ],
      "formula_columns": [
        {"header": "Rev x2", "formula": "={rev}{row}*2", "format": "currency"}
      ],
      "total_row": true
    }
  ]
}
```

Run: `python scripts/build_workbook.py --spec spec.json --out workbook.xlsx`
