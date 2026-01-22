# Test Duration Analysis - Overview

## Purpose

Understand test execution time patterns to identify:

- Slow tests that impact CI feedback time
- Duration trends over time
- Anomalies and outliers
- Opportunities for optimization

## Data Sources

```sql
-- Duration data from test_runs table
SELECT
    build_id,
    job_name,
    started_at,
    finished_at,
    EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds
FROM test_runs
WHERE finished_at IS NOT NULL
ORDER BY started_at;
```

## Metrics

**Test Run Duration**: Time from `started_at` to `finished_at`

**Aggregations**:

- Mean/Median duration
- P50, P90, P95, P99 percentiles
- Min/Max durations
- Standard deviation

**Dimensions**:

- Per job type
- Per PR
- Per date/week/month
- Per result (success vs. failure)

## Key Questions

1. How long do tests typically take?
2. Are tests getting slower over time?
3. Which job types are slowest?
4. Do failures take longer than successes?
5. Are there duration outliers?

## Findings

**Overall Statistics** (20,753 test runs with duration data):

- **Average Duration**: 35.0 minutes
- **Minimum**: -0.02 minutes (clock skew)
- **Maximum**: 724.5 minutes (12.1 hours)

**By Job Type**:

| Job Type | Runs | Avg Duration | Min | Max |
|----------|------|--------------|-----|-----|
| **e2e** | 5,505 | 82.1 min | 0.0 min | 635.8 min |
| **rhoai-e2e** | 715 | 74.2 min | 0.1 min | 199.0 min |
| **e2e-hypershift** | 939 | 69.1 min | 0.1 min | 724.5 min |
| **other** | 697 | 21.5 min | 0.1 min | 66.1 min |
| **bundle** | 4,204 | 13.7 min | 0.0 min | 354.6 min |
| **images** | 4,171 | 9.8 min | 0.1 min | 354.7 min |
| **image-mirror** | 4,522 | 9.5 min | 0.1 min | 80.4 min |

**By Result**:

- **FAILURE**: 75.7 min avg (longer due to timeouts)
- **SUCCESS**: 26.5 min avg
- **ABORTED**: 19.2 min avg (shorter, terminated early)

**Key Insights**:
- E2E tests take 1.1-1.4 hours on average
- Failed runs take **186% longer** than successful runs (75.7 vs 26.5 min)
- Maximum duration (12.1 hours) indicates severe timeout/hang issues in hypershift
- Build jobs (bundle, images) are fast (10-14 min avg)

### Weekly Duration Trends by Result Type

<!-- TODO: Add visualization
![Duration Trends](../images/duration_trends.png)
-->

**Trend Analysis**: Weekly average test duration data shows:

- **Failed tests**: Consistently take longest (60-90 minutes avg), likely due to timeout thresholds
- **Successful tests**: Faster and more stable (20-40 minutes avg)
- **Aborted tests**: Shortest duration (15-30 minutes), terminated early
- **Duration stability**: No significant improvement or degradation trends over time
- **Failure timeout impact**: The gap between successful and failed test durations suggests many failures hit timeout limits rather than failing fast

## Analysis Approach

1. Aggregate duration statistics
2. Plot time series trends
3. Break down by job type
4. Identify outliers
5. Correlate with failure rates

## Related

- [Time Series Analysis](timeseries.md)
- [Per-Suite Breakdown](per-suite.md)
- [SQL Queries](code.md)
