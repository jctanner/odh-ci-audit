# Failure Analysis - Time Series

## Overview

Track failure rates and patterns over time to identify trends and anomalies.

## Queries

### Daily Failure Rate

```sql
-- Daily failure rate by job type
SELECT
    DATE(started_at) as date,
    job_name,
    COUNT(*) as total_runs,
    SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
    SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) as failures,
    SUM(CASE WHEN result = 'ABORTED' THEN 1 ELSE 0 END) as aborted,
    ROUND(100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate
FROM test_runs
GROUP BY DATE(started_at), job_name
ORDER BY date, job_name;
```

### Weekly Trend

```sql
-- Weekly failure rate
SELECT
    DATE_TRUNC('week', started_at) as week,
    job_name,
    COUNT(*) as total_runs,
    SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) as failures,
    ROUND(100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate
FROM test_runs
GROUP BY DATE_TRUNC('week', started_at), job_name
ORDER BY week, job_name;
```

### Failure Type Trend

```sql
-- Daily breakdown by failure type (requires classification)
SELECT
    DATE(tr.started_at) as date,
    tc.failure_type,
    COUNT(*) as failures
FROM test_cases tc
JOIN test_runs tr ON tc.test_run_id = tr.id
WHERE tc.status = 'failed'
  AND tc.failure_type IS NOT NULL
GROUP BY DATE(tr.started_at), tc.failure_type
ORDER BY date, tc.failure_type;
```

## Python Analysis

```python
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine

engine = create_engine('postgresql://ci_audit:password@localhost/ci_audit')

def plot_failure_rate_trend():
    """Plot daily failure rate by job type."""
    query = """
        SELECT
            DATE(started_at) as date,
            job_name,
            COUNT(*) as total,
            SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) as failures
        FROM test_runs
        GROUP BY DATE(started_at), job_name
    """
    df = pd.read_sql(query, engine, parse_dates=['date'])
    df['failure_rate'] = 100.0 * df['failures'] / df['total']

    plt.figure(figsize=(14, 6))
    for job in df['job_name'].unique():
        job_data = df[df['job_name'] == job]
        plt.plot(job_data['date'], job_data['failure_rate'], label=job, marker='o', markersize=3)

    plt.xlabel('Date')
    plt.ylabel('Failure Rate (%)')
    plt.title('Test Failure Rate Trends')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('failure_rate_trends.png', dpi=300)

def plot_failure_type_stacked():
    """Plot stacked area chart of failure types over time."""
    query = """
        SELECT
            DATE(tr.started_at) as date,
            tc.failure_type,
            COUNT(*) as count
        FROM test_cases tc
        JOIN test_runs tr ON tc.test_run_id = tr.id
        WHERE tc.status = 'failed'
          AND tc.failure_type IS NOT NULL
        GROUP BY DATE(tr.started_at), tc.failure_type
    """
    df = pd.read_sql(query, engine, parse_dates=['date'])

    # Pivot for stacked area plot
    pivot = df.pivot(index='date', columns='failure_type', values='count').fillna(0)

    plt.figure(figsize=(14, 6))
    pivot.plot.area(stacked=True, alpha=0.7, ax=plt.gca())
    plt.xlabel('Date')
    plt.ylabel('Number of Failures')
    plt.title('Failure Types Over Time')
    plt.legend(title='Failure Type', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig('failure_types_stacked.png', dpi=300)

if __name__ == '__main__':
    plot_failure_rate_trend()
    plot_failure_type_stacked()
```

## Visualization

From [Common Failures](../../findings/common-failures.md), [Flake Rate](../../findings/flake-rate.md), and [Infrastructure Issues](../../findings/infrastructure.md):

### Weekly Failure Rate Trends

![Weekly Failure Rate](../../images/weekly_failure_rate.png)

The stacked area and line chart visualization shows:
- **Stacked area (top)**: Result distribution over time (success, failure, aborted)
- **Line chart (bottom)**: Failure rate percentage trend
- **High variability**: Failure rates fluctuate significantly week-to-week with no clear improvement trend
- **Consistent presence**: Failures (red) and aborted runs (gray) present throughout entire 6-month period

### Job Type Failure Trends

![Job Type Failure Trends](../../images/job_type_failure_trends.png)

Failure rate by job type over time reveals:
- **E2E tests** (standard and hypershift): Consistently high failure rates (40-70%) throughout collection period
- **RHOAI E2E tests**: Similar pattern to standard e2e, indicating shared infrastructure challenges
- **Bundle and image jobs**: Much lower and more stable failure rates (5-20%)
- **High week-to-week variance**: E2E tests show erratic behavior, suggesting environment-dependent failures
- **No improvement trend**: Rates remain relatively flat across 6-month period

### Infrastructure Failure Trends Over Time

From [Infrastructure Issues](../../findings/infrastructure.md), weekly infrastructure failure breakdown:

**Sample Weekly Data** (first 10 weeks, July-September 2025):

| Week Starting | Total Failures | Timeout Failures | Image Pull Failures | Timeout % |
|---------------|----------------|------------------|---------------------|-----------|
| 2025-07-14 | 182 | 111 | 58 | 61.0% |
| 2025-07-21 | 147 | 83 | 17 | 56.5% |
| 2025-07-28 | 90 | 73 | 12 | 81.1% |
| 2025-08-04 | 211 | 161 | 32 | 76.3% |
| 2025-08-11 | 105 | 72 | 25 | 68.6% |
| 2025-08-18 | 114 | 70 | 45 | 61.4% |
| 2025-08-25 | 90 | 78 | 2 | 86.7% |
| 2025-09-01 | 141 | 109 | 26 | 77.3% |
| 2025-09-08 | 231 | 198 | 25 | 85.7% |
| 2025-09-15 | 327 | 250 | 42 | 76.5% |

**Observations**:
- Timeout rate variability: 56.5% - 86.7% across weeks
- Image pull spikes: Some weeks show unusually high image pull failures (58, 45)
- Volume fluctuations: Total failures vary 90-327 per week
- **No clear improvement**: Issues persist throughout entire 6-month period

## Anomaly Detection

### Statistical Outliers

```sql
-- Days with unusually high failure rates
WITH daily_stats AS (
    SELECT
        DATE(started_at) as date,
        100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*) as failure_rate
    FROM test_runs
    GROUP BY DATE(started_at)
),
stats AS (
    SELECT
        AVG(failure_rate) as mean_rate,
        STDDEV(failure_rate) as stddev_rate
    FROM daily_stats
)
SELECT
    ds.date,
    ROUND(ds.failure_rate, 2) as failure_rate,
    ROUND(s.mean_rate, 2) as mean_rate,
    ROUND((ds.failure_rate - s.mean_rate) / s.stddev_rate, 2) as std_devs
FROM daily_stats ds
CROSS JOIN stats s
WHERE ABS(ds.failure_rate - s.mean_rate) > 2 * s.stddev_rate
ORDER BY ABS(std_devs) DESC;
```

## Correlation Analysis

### Failure Rate vs. PR Volume

```sql
-- Correlate failure rate with PR volume
SELECT
    DATE(started_at) as date,
    COUNT(DISTINCT pr_number) as unique_prs,
    COUNT(*) as total_runs,
    ROUND(100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate
FROM test_runs
GROUP BY DATE(started_at)
ORDER BY date;
```

## Findings

From analysis of failure trends across the 6-month period (July 2025 - January 2026):

### Is failure rate trending up or down?

**No clear trend - failure rate is STABLE (not improving, not worsening)**:

- Overall failure rate: **~20-40%** across the 6-month period
- Weekly variation: Significant fluctuation (30-70% depending on week and job type)
- **No systematic improvement**: Infrastructure issues persist throughout entire period
- **No systematic degradation**: Not getting worse, just consistently problematic

From [Infrastructure Issues](../../findings/infrastructure.md):
- Timeout rates vary 56.5%-86.7% week-to-week with no trend
- Image pull failures spike randomly (58 one week, 2 another week, 45 another)
- Total failure volume fluctuates 90-327 per week

**Conclusion**: The CI system has **chronic, persistent issues** that are not being addressed over time.

### Are there weekly patterns (e.g., Mondays worse)?

**Time-of-DAY patterns are more significant than day-of-week patterns**:

From [Time Cost Analysis](../../findings/time-cost.md), hourly success rate analysis:

| Time Period (UTC) | EST/EDT | Success Rate | Pattern |
|-------------------|---------|--------------|---------|
| **Best: 5-7 AM** | 12-2 AM EST / 1-3 AM EDT | **70.8%** | Early morning, low usage |
| **Worst: 3 PM** | 10 AM EST / 11 AM EDT | **52.6%** | Peak business hours |
| **Worst: 9 PM** | 4 PM EST / 5 PM EDT | **49.7%** | Evening peak |
| Business hours (1-4 PM) | 8-11 AM EST / 9 AM-12 PM EDT | 52-58% | High infrastructure load |

**21% variance in success rate** between best (70%) and worst (50%) times.

**Implication**: Weekdays during business hours (9 AM - 6 PM UTC / 4 AM - 1 PM EST / 5 AM - 2 PM EDT) likely show worse failure rates than weekends/off-hours due to infrastructure contention.

While explicit day-of-week analysis wasn't performed, the time-of-day correlation strongly suggests **weekdays are worse than weekends** due to higher cluster usage during business hours.

### Which failure types are increasing?

**None are significantly increasing - all failure types remain persistent**:

From [Common Failures](../../findings/common-failures.md) and [Infrastructure Issues](../../findings/infrastructure.md):

| Failure Type | Trend | Notes |
|--------------|-------|-------|
| **Infrastructure (87.6%)** | **Flat/stable** | Timeouts, pod startup, image pulls, network - no improvement |
| Timeout failures (69.5%) | **Flat/stable** | Varies 56.5%-86.7% week-to-week, no trend |
| Pod startup (51.3%) | **Flat/stable** | Persistent throughout period |
| Image pulls (17.6%) | **Spiky** | Random spikes (58→17→12→32...), not trending |
| Network (11.2%) | **Flat/stable** | Consistent presence |
| Configuration (12.3%) | **Flat/stable** | No significant change |
| Code regressions (0.1%) | **Flat/minimal** | Only 4 failures total |

**Conclusion**: Infrastructure failures dominate (87.6%) and remain at that level throughout the entire 6-month period. No failure type is getting better OR worse - they're all persistently present.

### Are there specific dates with anomalies?

**Yes - random weekly anomalies, but no consistent pattern**:

From [Infrastructure Issues](../../findings/infrastructure.md) weekly breakdown:

**Anomalous weeks identified**:

1. **2025-08-25** (week of Aug 25):
   - 86.7% timeout rate (highest)
   - Only 2 image pull failures (lowest)
   - 90 total failures (low volume)

2. **2025-09-15** (week of Sept 15):
   - 327 total failures (highest volume in sample)
   - 250 timeout failures (highest absolute count)

3. **2025-07-14** (week of July 14):
   - 58 image pull failures (highest spike)

4. **2025-08-18** (week of Aug 18):
   - 45 image pull failures (second spike)

**Pattern**: Anomalies appear to be **random/environmental** rather than systematic:
- No correlation with specific dates
- No monthly pattern
- No improvement after high-failure weeks
- Suggests external factors (registry issues, cluster degradation, network problems)

**From [Common Failures](../../findings/common-failures.md)**: Job type failure trends show high variability week-to-week with no improvement, confirming random environmental factors rather than code-related patterns.

### Additional Finding: Failure Rate by Job Type is Remarkably Consistent

From [Common Failures](../../findings/common-failures.md):

**E2E jobs**:
- Consistently 40-70% failure rate across entire period
- No improvement despite 6 months of development

**Build jobs** (bundle, images, image-mirror):
- Consistently 2-4% failure rate
- Highly stable and reliable throughout

**Implication**: The failure patterns are **systemic to job type**, not improving or degrading over time. E2E infrastructure is chronically unreliable, while build infrastructure is consistently solid.

## Related

- [Overview](overview.md)
- [Classification](classification.md)
- [Per-Test Breakdown](per-test.md)
- [SQL & Python](code.md)
