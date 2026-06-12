# Authoring HTML for render_pdf.py

`render_pdf.py` accepts HTML and renders it to a styled A4 PDF. It works in
two modes.

## Fragment mode (recommended)

Write the report body only — no `<html>`/`<head>`. The script wraps it in the
print template and, if you pass `--title`, prepends a cover block.

```html
<h1>Q1 2026 Report</h1>
<p class="muted">Prepared by the growth team</p>

<h2>Summary</h2>
<p>Signups doubled after the referral launch. Activation rose from 41% to 58%.</p>

<h2>Metrics</h2>
<table>
  <tr><th>Metric</th><th>Q4</th><th>Q1</th></tr>
  <tr><td>Signups</td><td>1,200</td><td>3,600</td></tr>
  <tr><td>Activation</td><td>41%</td><td>58%</td></tr>
</table>
```

```
python scripts/render_pdf.py --html body.html --out report.pdf \
  --title "Q1 2026 Report" --subtitle "Product & Growth" --accent "#2563eb"
```

## Full-document mode

Pass a complete `<!DOCTYPE html>…</html>` document (e.g. one authored with
`frontend-design`). The script injects the base print CSS into the existing
`<head>` so page size, margins, and the footer page number still apply, then
renders it as-is. Your own `<style>` wins for everything else.

## What the base stylesheet provides

- **Page setup:** A4, comfortable margins, a `page / pages` footer.
- **Type scale:** `h1` 22pt, `h2` 15pt (underlined), `h3` 12pt, body 11pt,
  all in one sans stack. Override with your own CSS in full-document mode.
- **Accent color:** set with `--accent`; applied to all headings and the cover
  title. Default `#2563eb`.
- **Tables:** bordered, striped header, `break-inside: avoid` per row so a row
  never splits across a page.
- **Page-break hygiene:** `break-after: avoid` on headings so they don't
  strand at a page bottom.
- **Helper class:** `.muted` for secondary gray text.

## Images

There is no network at render time. Save any image (e.g. a `chart-maker` PNG)
under the workbench dir and reference it by absolute path:

```html
<img src="/workspace/chart.png" style="width:100%">
```

Remote `src` URLs will fail to load — embed locally instead.

## Inputs / outputs

- Input: `--html PATH` or `--html-stdin`.
- Output: `--out report.pdf`.
- Cover (fragment mode): `--title`, `--subtitle`, `--date YYYY-MM-DD`
  (defaults to today).
- `--accent` hex color.
