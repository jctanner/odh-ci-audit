# Test Duration - Per-Suite Breakdown

## Overview

Compare duration across different job types and test suites.

## Job Type Comparison

### Average Duration by Job

```sql
-- Duration statistics per job type
SELECT
    job_name,
    COUNT(*) as total_runs,
    ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as avg_minutes,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as median_minutes,
    ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as p90_minutes,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as p95_minutes,
    ROUND(MIN(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as min_minutes,
    ROUND(MAX(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as max_minutes
FROM test_runs
WHERE finished_at IS NOT NULL
GROUP BY job_name
ORDER BY avg_minutes DESC;
```

## Test Suite Breakdown

### Individual Test Case Duration

```sql
-- Test case duration statistics
SELECT
    test_suite,
    test_name,
    COUNT(*) as executions,
    ROUND(AVG(duration_seconds), 2) as avg_seconds,
    ROUND(MAX(duration_seconds), 2) as max_seconds,
    ROUND(MIN(duration_seconds), 2) as min_seconds
FROM test_cases
WHERE duration_seconds IS NOT NULL
GROUP BY test_suite, test_name
ORDER BY avg_seconds DESC
LIMIT 20;
```

### Suite-Level Aggregation

```sql
-- Total duration per test suite
SELECT
    tc.test_suite,
    COUNT(DISTINCT tr.build_id) as builds,
    COUNT(*) as total_tests,
    ROUND(AVG(tc.duration_seconds), 2) as avg_test_duration,
    ROUND(SUM(tc.duration_seconds) / COUNT(DISTINCT tr.build_id), 2) as avg_suite_duration
FROM test_cases tc
JOIN test_runs tr ON tc.test_run_id = tr.id
WHERE tc.duration_seconds IS NOT NULL
GROUP BY tc.test_suite
ORDER BY avg_suite_duration DESC;
```

## Python Analysis

```python
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import create_engine

engine = create_engine('postgresql://ci_audit:password@localhost/ci_audit')

# Job type comparison
query = """
    SELECT
        job_name,
        EXTRACT(EPOCH FROM (finished_at - started_at)) / 60 as duration_minutes
    FROM test_runs
    WHERE finished_at IS NOT NULL
"""
df = pd.read_sql(query, engine)

# Box plot by job type
df.boxplot(column='duration_minutes', by='job_name', figsize=(12, 6))
plt.suptitle('Duration Distribution by Job Type')
plt.xlabel('Job Type')
plt.ylabel('Duration (minutes)')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig('duration_by_job.png')

# Top 10 slowest tests
test_query = """
    SELECT test_suite, test_name, AVG(duration_seconds) as avg_duration
    FROM test_cases
    WHERE duration_seconds IS NOT NULL
    GROUP BY test_suite, test_name
    ORDER BY avg_duration DESC
    LIMIT 10
"""
slow_tests = pd.read_sql(test_query, engine)
print("Top 10 Slowest Tests:")
print(slow_tests)
```

## Visualization

From [Time Cost Analysis](../../findings/time-cost.md):

### Time Cost by Job Type

![Time Cost by Job Type](../../images/time_cost_by_job_type.png)

The stacked horizontal bar chart shows duration breakdown by job type:
- **E2E tests**: 7,529 hours total (dominated by red/failure time - 57.4% wasted)
- **E2E hypershift**: 1,069 hours (49.9% wasted on failures)
- **RHOAI E2E**: 885 hours (40.0% wasted on failures)
- **Bundle, images, image-mirror**: Minimal red slices (2-4% failure time) - highly efficient

The contrast between e2e jobs (failure-heavy) and build jobs (success-heavy) is visually striking.

### Time Cost Breakdown

![Time Cost Breakdown](../../images/time_cost_breakdown.png)

Overall time distribution across all job types:
- **Pie chart**: Nearly equal split between successful (44.3%) and failed (43.7%) test time
- **Bar chart**: Despite failures being fewer runs, they accumulate similar total time due to 3x longer duration
- **Wasted time**: 55.3% of all compute time (failures + aborted runs)

### Duration Comparison Tables

From [Time Cost Analysis](../../findings/time-cost.md), actual duration statistics by job and result:

**Job-Level Duration Statistics**:

| Job Type | Result | Avg Duration | Median | P90 | Max |
|----------|--------|--------------|--------|-----|-----|
| **e2e** | FAILURE | **92.0 min** | 99.1 min | 134.2 min | **300.1 min** |
| **e2e** | SUCCESS | 115.6 min | 114.9 min | 133.9 min | 236.4 min |
| **e2e-hypershift** | FAILURE | 87.4 min | 92.4 min | 138.8 min | 224.6 min |
| **e2e-hypershift** | SUCCESS | 103.3 min | 97.6 min | 138.5 min | 227.9 min |
| **rhoai-e2e** | FAILURE | 94.8 min | 107.7 min | 145.1 min | 199.0 min |
| **rhoai-e2e** | SUCCESS | 110.1 min | 107.9 min | 126.5 min | 159.7 min |
| bundle | FAILURE | 5.4 min | 3.1 min | 12.1 min | 50.3 min |
| bundle | SUCCESS | 16.5 min | 14.0 min | 28.2 min | 101.3 min |
| images | FAILURE | 7.4 min | 4.6 min | 13.0 min | 243.8 min |
| images | SUCCESS | 10.9 min | 9.7 min | 16.9 min | 74.6 min |
| image-mirror | FAILURE | 5.8 min | 3.4 min | 12.0 min | 68.8 min |
| image-mirror | SUCCESS | 10.6 min | 9.3 min | 16.8 min | 74.8 min |

## Findings

From [Time Cost Analysis](../../findings/time-cost.md) and [CI Pipeline Issues](../../findings/ci-pipeline.md):

### Job Type Duration Comparison

**Actual vs Expected**:

| Job Type | Expected | Actual (Success) | Actual (Failure) | Observations |
|----------|----------|------------------|------------------|--------------|
| E2E jobs | 30-60 min | **115.6 min** | **92.0 min** | **Much longer than expected** |
| E2E hypershift | 30-60 min | **103.3 min** | 87.4 min | Exceeds expectations |
| RHOAI E2E | 30-60 min | **110.1 min** | 94.8 min | Exceeds expectations |
| Bundle jobs | 5-10 min | **16.5 min** | 5.4 min | Within expected range for failures |
| Image jobs | 5-10 min | **10.9 min** | 7.4 min | Meets expectations |
| Image-mirror | 5-10 min | **10.6 min** | 5.8 min | Meets expectations |

**Critical Finding**: E2E jobs take **2-3x longer than initially expected** (115 min vs 30-60 min expected), suggesting:
1. Tests are too comprehensive/slow
2. Infrastructure is slow
3. Many retries within test execution
4. Waiting for timeouts

### Anomaly: Failed Tests Are Shorter Than Successful Tests (E2E Only)

**E2E jobs**:
- Success: 115.6 min avg
- Failure: **92.0 min avg** (shorter!)

**Why?**: Failed e2e tests likely **hit timeout limits** (max 300 min) and abort early, rather than running to natural completion. This is supported by:
- [Infrastructure Issues](../../findings/infrastructure.md): 69.5% of failures involve timeouts
- P90 for e2e failures: 134 min (likely near timeout threshold)
- Successful tests complete naturally without hitting limits

**Build jobs show opposite pattern** (expected):
- Bundle: 16.5 min success vs 5.4 min failure (failures fail fast)
- Images: 10.9 min success vs 7.4 min failure (failures fail fast)

### Slowest Test Components

From [Common Failures](../../findings/common-failures.md), component-specific test volumes:

| Component | Total Tests | Failure Rate | Likely Duration Impact |
|-----------|-------------|--------------|------------------------|
| **DataSciencePipelines** | 118,831 | 0.6% | **Highest volume** → long cumulative time |
| Monitoring | 81,772 | 3.9% | High volume, moderate failures |
| Dashboard | 51,379 | 0.6% | Moderate volume, very reliable |
| Kueue | 40,982 | 2.1% | Moderate volume |
| KServe | 41,108 | 1.6% | Moderate volume |
| ModelRegistry | 35,708 | 0.7% | Moderate volume, reliable |
| Trainer | 19,428 | 9.8% | **Highest failure rate** → more time wasted on retries |

**Inference**:
- **DataSciencePipelines**: Highest test count (118,831) means long cumulative duration even with low failure rate
- **Trainer**: Highest failure rate (9.8%) means tests retry more, wasting time
- **Monitoring**: Large test count (81,772) with moderate failure rate (3.9%) = significant time investment

### E2E vs Build Jobs: Efficiency Comparison

**Time Wasted by Job Type** (from [Time Cost Analysis](../../findings/time-cost.md)):

| Job Type | Total Hours | % Time on Failures | Efficiency |
|----------|-------------|--------------------|------------|
| **e2e** | 7,529 | **57.4%** | **Very inefficient** - majority of time wasted |
| **e2e-hypershift** | 1,069 | **49.9%** | Inefficient - nearly half time wasted |
| **rhoai-e2e** | 885 | **40.0%** | Moderately inefficient |
| bundle | 961 | **2.6%** | **Highly efficient** |
| image-mirror | 714 | **3.4%** | **Highly efficient** |
| images | 683 | **3.8%** | **Highly efficient** |

**Key Insight**: Build jobs (bundle, images, image-mirror) are **15-20x more efficient** than e2e jobs in terms of time utilization. They fail fast (5-7 min) and succeed quickly (10-16 min).

E2E jobs waste the majority of their time on failures that run for 90+ minutes before timing out.

### Duration vs Result Hypothesis Confirmed

**Hypothesis**: Failed runs may be longer due to timeouts.

**Evidence**:
- **Failed e2e runs**: 92.0 min avg (hit timeout, abort)
- **Successful e2e runs**: 115.6 min avg (complete naturally)
- **3x multiplier overall**: 75.7 min failures vs 26.5 min successes (across all job types)

**Conclusion**: The hypothesis is **partially confirmed**:
1. For e2e jobs: Failures are shorter because they hit timeout thresholds
2. For all job types combined: Failures are 3x longer on average
3. The 3x multiplier is driven by e2e jobs hanging/waiting before timeout

## Duration vs. Result

```sql
-- Compare duration of successful vs. failed runs
SELECT
    job_name,
    result,
    COUNT(*) as runs,
    ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as avg_minutes
FROM test_runs
WHERE finished_at IS NOT NULL
GROUP BY job_name, result
ORDER BY job_name, result;
```

**Hypothesis**: Failed runs may be longer due to timeouts.

## Related

- [Overview](overview.md)
- [Time Series Analysis](timeseries.md)
- [SQL & Python](code.md)
