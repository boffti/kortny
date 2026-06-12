---
name: financial-statements
description: Use when asked to analyze a financial statement, interpret income statement or balance sheet figures, calculate key financial ratios, or produce a plain-language summary of a company's financial position for a business audience.
metadata:
  version: 1.0.0
  display_name: Financial Statements
  tags: finance, financial, income-statement, balance-sheet, cash-flow, ratios, earnings, analysis
---

## Goal

Translate raw financial statements into business-readable analysis — ratios, trends, and the one-paragraph story a board member would recognize.

## Steps

1. **Identify the statement type(s)**: income statement, balance sheet, cash flow statement, or a combination. Note the period (annual/quarterly) and currency.
2. **Extract the key figures** — do not summarize without numbers. See `references/key-metrics.md` for the standard metric set by statement type.
3. **Calculate the ratios relevant to the request**:
   - *Profitability*: gross margin, operating margin, net margin, EBITDA margin.
   - *Liquidity*: current ratio, quick ratio.
   - *Leverage*: debt-to-equity, interest coverage.
   - *Efficiency*: asset turnover, days sales outstanding (if applicable).
4. **Compare to context**: year-over-year delta, industry benchmark if known. If no benchmark is available, say so.
5. **Write the plain-language summary**: one paragraph, three or fewer sentences, stating the financial story (growing profitably, burning cash, improving margins, etc.) with the two most important numbers cited.
6. **Flag anything anomalous**: one-time items, restatements, unusual line items. Do not smooth them into the summary.

## Output shape

- Lead with the one-paragraph story.
- Follow with a ratios table (metric, value, YoY change, benchmark if known).
- Close with 2-3 watch-list items — things that would change the story if they move.

## Rules

- Never fabricate financial figures. If a line item is missing, note it as "not disclosed" rather than estimating.
- Ratios with a zero denominator get flagged as "N/M (not meaningful)", not left blank.
- If the data is a snippet or partial statement, say so at the top before any analysis.
- Tax treatment, stock-based comp, and lease adjustments are material — name them when present.
