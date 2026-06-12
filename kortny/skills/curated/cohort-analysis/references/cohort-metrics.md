# Cohort Metrics Reference

## Retention rate
**Retention at period N** = Users from cohort still active at period N / Cohort size at period 0

*Example: "40% of the January cohort (n=200) was still active at month 3."*

## Churn rate (cohort-level)
**Churn at period N** = 1 − Retention at period N

**Month-over-month churn** = (Users active at start of month − Users active at end of month) / Users active at start of month

## Activation rate
**Activation rate** = Users who completed the activation event / Total users in cohort

*Activation event must be defined before running the analysis — e.g., "created first project", "invited a teammate", "ran first report".*

## LTV by cohort
**Cumulative LTV at month N** = Sum of all revenue from cohort through month N / Cohort size

*Track month by month to see when LTV curves flatten (indicates churn has stabilized).*

## Cohort table format (standard)
Rows = cohorts (e.g., "Jan 2025", "Feb 2025")
Columns = periods since signup (Month 0, Month 1, Month 2, …)
Cells = retention % or count

| Cohort | M0 | M1 | M2 | M3 | M6 | M12 |
|---|---|---|---|---|---|---|
| Jan 2025 (n=200) | 100% | 72% | 58% | 51% | 44% | 39% |
| Feb 2025 (n=175) | 100% | 68% | 54% | 48% | — | — |

## Reading the table
- **Flat after M3**: healthy SaaS — early churn resolved, long-term customers retained.
- **Steady decline with no floor**: poor product-market fit or onboarding failure.
- **Improving cohorts over time**: product or onboarding improvements are working.
- **One cohort outlier**: check acquisition source — was that a different channel, campaign, or price point?

## Minimum sample sizes
- For directional signal: n ≥ 30 per cohort.
- For statistical significance: n ≥ 100 per cohort (for 80% power at typical retention rates).
- Flag cohorts below n=30 as insufficient for conclusions.
