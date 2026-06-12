# RevOps Metric Formulas

## Pipeline metrics
- **Pipeline coverage ratio** = Total pipeline value / Quota remaining
  - Healthy: ≥3x for early quarter, ≥2x for late quarter.
- **Win rate** = Closed-Won / (Closed-Won + Closed-Lost) in period
- **Average deal size** = Total Closed-Won ARR / Number of deals
- **Sales cycle length** = Average days from opportunity created → Closed-Won

## Funnel conversion rates
- **Lead → MQL** = MQLs / Total leads
- **MQL → SQL** = SQLs / MQLs
- **SQL → Opportunity** = Opportunities created / SQLs
- **Opportunity → Close** = Closed-Won / Opportunities

## Velocity
- **Pipeline velocity** = (# Opportunities × Win rate × Avg deal size) / Avg sales cycle days
- Used to model how changes in any one variable affect revenue.

## Quota attainment
- **Attainment %** = Closed-Won ARR / Quota × 100
- **Ramp-adjusted quota**: If reps are in ramp, note the ramp factor applied.

## Forecast categories
| Stage | Meaning |
|---|---|
| Commit | Rep commits to close this period — high confidence |
| Best case | Could close; needs work |
| Pipeline | Qualified, not forecasted |
| Omitted | Unlikely this period |

## Common red flags
- Close dates bunched at end of quarter ("hockey stick") → unreliable forecast.
- Pipeline coverage <2x with <30 days in quarter → at-risk quarter.
- Win rate declining over 3 quarters → product-market or competitive issue.
- ACV trending down → discounting or downmarket drift.
