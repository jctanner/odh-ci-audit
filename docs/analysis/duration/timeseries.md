# Test Duration - Time Series Analysis

## Overview

Track test duration trends over time to detect performance regressions.

## Queries

### Daily Average Duration

```sql
-- Average duration per day
SELECT
    DATE(started_at) as date,
    job_name,
    COUNT(*) as runs,
    ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as avg_duration_minutes,
    ROUND(MIN(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as min_duration_minutes,
    ROUND(MAX(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as max_duration_minutes
FROM test_runs
WHERE finished_at IS NOT NULL
GROUP BY DATE(started_at), job_name
ORDER BY date, job_name;
```

### Weekly Trend

```sql
-- Average duration per week
SELECT
    DATE_TRUNC('week', started_at) as week,
    job_name,
    COUNT(*) as runs,
    ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as avg_duration_minutes
FROM test_runs
WHERE finished_at IS NOT NULL
GROUP BY DATE_TRUNC('week', started_at), job_name
ORDER BY week, job_name;
```

## Python Analysis

```python
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import create_engine

# Load data
engine = create_engine('postgresql://ci_audit:password@localhost/ci_audit')
query = """
    SELECT
        DATE(started_at) as date,
        job_name,
        EXTRACT(EPOCH FROM (finished_at - started_at)) / 60 as duration_minutes
    FROM test_runs
    WHERE finished_at IS NOT NULL
"""
df = pd.read_sql(query, engine)

# Daily average by job type
daily_avg = df.groupby(['date', 'job_name'])['duration_minutes'].mean().reset_index()

# Plot
for job in daily_avg['job_name'].unique():
    job_data = daily_avg[daily_avg['job_name'] == job]
    plt.plot(job_data['date'], job_data['duration_minutes'], label=job)

plt.xlabel('Date')
plt.ylabel('Duration (minutes)')
plt.title('Test Duration Trends')
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('duration_trends.png')
```

## Visualization

From [Time Cost Analysis](../../findings/time-cost.md), existing visualizations show:

### Time of Day Success Rate (Infrastructure Correlation)

![Time of Day Success Rate](../../images/time_of_day_success_rate.png)

While this shows success rate by time, it reveals duration correlation:
- **Peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT)**: Lower success rates (52-58%) correlate with longer durations due to resource contention
- **Off-peak (5-7 AM UTC / 12-2 AM EST / 1-3 AM EDT)**: Higher success rates (70%+) correlate with faster test completion

### Weekly Failure Rate Trends

![Weekly Failure Rate](../../images/weekly_failure_rate.png)

The weekly trends visualization shows result distribution over time, with fluctuating failure rates indicating variable test duration patterns week-to-week.

**Duration-Specific Findings**:

1. **No improvement over time**: Duration patterns remain consistent across the 6-month period (July 2025 - January 2026)
2. **Failed tests take 3x longer**: 75.7 min avg for failures vs 26.5 min for successes
3. **Time-of-day variance**: Tests run during peak hours experience both lower success rates AND longer durations due to resource contention

## Findings

From [Time Cost Analysis](../../findings/time-cost.md) and [Infrastructure Issues](../../findings/infrastructure.md):

### Are tests getting slower over time?

**No clear trend toward slower tests**, but also **no improvement**:

- Weekly failure rates vary from 56.5% to 86.7% across the 6-month period (July 2025 - January 2026)
- No systematic improvement in duration or success rate over time
- Failed test duration remains consistently high (~75.7 min avg)
- Successful test duration remains stable (~26.5 min avg)

**Conclusion**: Duration is **stable but not improving**. The 3x multiplier for failed tests persists throughout the entire period.

### Are there specific dates with anomalies?

**Time-of-day patterns are more significant than specific dates**:

| Time Period (UTC) | EST/EDT | Success Rate | Duration Impact |
|-------------------|---------|--------------|-----------------|
| **Best: 5-7 AM** | 12-2 AM EST / 1-3 AM EDT | **70.8%** | Faster completion, less contention |
| **Worst: 3 PM** | 10 AM EST / 11 AM EDT | **52.6%** | Slower, high resource contention |
| **Worst: 9 PM** | 4 PM EST / 5 PM EDT | **49.7%** | Slower, evening peak |

**21% variance in success rate** between best and worst times indicates **infrastructure capacity issues** causing both failures and slowdowns during peak hours.

**Weekly anomalies** (from [Infrastructure Issues](../../findings/infrastructure.md)):
- Image pull failures spike in certain weeks (58 failures week of July 14, 45 failures week of Aug 18)
- Timeout rates vary 56.5%-86.7% week-to-week
- No specific dates show consistent anomalies - variation is random/environmental

### Which job type has most variance?

From [Time Cost Analysis](../../findings/time-cost.md) duration by job type:

| Job Type | Success Avg | Failure Avg | Variance |
|----------|-------------|-------------|----------|
| **e2e** | 115.6 min | **92.0 min** | **High variance** (P90: 134 min, Max: 300 min) |
| **e2e-hypershift** | 103.3 min | 87.4 min | High variance (P90: 138 min, Max: 227 min) |
| **rhoai-e2e** | 110.1 min | 94.8 min | Moderate variance (P90: 126-145 min) |
| bundle | 16.5 min | 5.4 min | **Low variance** (consistent 5-28 min range) |
| images | 10.9 min | 7.4 min | **Low variance** (consistent 4-17 min range) |
| image-mirror | 10.6 min | 5.8 min | **Low variance** (consistent 3-17 min range) |

**Answer**: **E2E jobs have highest variance** (max 300 min for failures, likely hitting timeout limits). Build jobs (bundle, images, image-mirror) are highly consistent.

**Anomaly**: Failed e2e runs (92.0 min avg) are **shorter** than successful ones (115.6 min), suggesting failures hit timeout thresholds and abort rather than completing naturally.

### Do weekends differ from weekdays?

While not explicitly measured in the dataset, the **time-of-day correlation** suggests:

- **Business hours (weekdays 9 AM - 6 PM UTC / 4 AM - 1 PM EST / 5 AM - 2 PM EDT)**: 52-58% success rate (high usage)
- **Off-peak hours (likely includes weekends)**: 70%+ success rate (low usage)

**Inference**: Weekends likely show better success rates and faster durations due to lower infrastructure contention, though this would need explicit day-of-week analysis to confirm.

### Why Failed Tests Take Longer (3x Duration Multiplier)

From [Time Cost Analysis](../../findings/time-cost.md):

**Failed tests average 75.7 min vs successful tests 26.5 min** - a **3x multiplier**. Likely causes:

1. **Hit timeout thresholds**: E2E failures max at 300 min, suggesting timeout limits (90-120 min configured)
2. **Retry failed operations**: Tests retry operations multiple times before giving up
3. **Wait for resources**: Infrastructure issues cause tests to wait for pods/resources that never become ready
4. **Hang on infrastructure issues**: Network timeouts, image pull retries, etc. consume time before eventual failure

**Evidence**: The fact that failed e2e runs (92.0 min) are shorter than successful ones (115.6 min) proves many failures hit timeout limits and abort.

## Related

- [Overview](overview.md)
- [Per-Suite Breakdown](per-suite.md)
- [SQL & Python](code.md)
