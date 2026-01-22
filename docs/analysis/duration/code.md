# Test Duration - SQL & Python

## Complete SQL Query Library

### Basic Duration Statistics

```sql
-- Overall duration statistics
SELECT
    COUNT(*) as total_runs,
    ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as avg_minutes,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as median_minutes,
    ROUND(STDDEV(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as stddev_minutes
FROM test_runs
WHERE finished_at IS NOT NULL;
```

### Duration by Job and Result

```sql
-- Duration breakdown by job type and result
SELECT
    job_name,
    result,
    COUNT(*) as runs,
    ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as avg_minutes,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as median_minutes,
    ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as p90_minutes,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as p95_minutes
FROM test_runs
WHERE finished_at IS NOT NULL
GROUP BY job_name, result
ORDER BY job_name, result;
```

### Time Series with Moving Average

```sql
-- Daily duration with 7-day moving average
WITH daily_duration AS (
    SELECT
        DATE(started_at) as date,
        job_name,
        AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60) as avg_minutes
    FROM test_runs
    WHERE finished_at IS NOT NULL
    GROUP BY DATE(started_at), job_name
)
SELECT
    date,
    job_name,
    ROUND(avg_minutes, 2) as daily_avg,
    ROUND(AVG(avg_minutes) OVER (
        PARTITION BY job_name
        ORDER BY date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2) as moving_avg_7d
FROM daily_duration
ORDER BY job_name, date;
```

### Duration Outliers

```sql
-- Find runs with duration > 2 standard deviations from mean
WITH stats AS (
    SELECT
        job_name,
        AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60) as mean_minutes,
        STDDEV(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60) as stddev_minutes
    FROM test_runs
    WHERE finished_at IS NOT NULL
    GROUP BY job_name
)
SELECT
    tr.build_id,
    tr.pr_number,
    tr.job_name,
    ROUND(EXTRACT(EPOCH FROM (tr.finished_at - tr.started_at)) / 60, 2) as duration_minutes,
    ROUND(s.mean_minutes, 2) as mean_minutes,
    ROUND((EXTRACT(EPOCH FROM (tr.finished_at - tr.started_at)) / 60 - s.mean_minutes) / s.stddev_minutes, 2) as std_devs
FROM test_runs tr
JOIN stats s ON tr.job_name = s.job_name
WHERE tr.finished_at IS NOT NULL
  AND ABS(EXTRACT(EPOCH FROM (tr.finished_at - tr.started_at)) / 60 - s.mean_minutes) > 2 * s.stddev_minutes
ORDER BY ABS(std_devs) DESC;
```

### Test Case Duration Analysis

```sql
-- Slowest test cases across all runs
SELECT
    test_suite,
    test_name,
    COUNT(*) as executions,
    ROUND(AVG(duration_seconds), 2) as avg_seconds,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_seconds), 2) as median_seconds,
    ROUND(MAX(duration_seconds), 2) as max_seconds,
    ROUND(MIN(duration_seconds), 2) as min_seconds
FROM test_cases
WHERE duration_seconds IS NOT NULL
GROUP BY test_suite, test_name
HAVING COUNT(*) >= 10  -- Only tests run at least 10 times
ORDER BY avg_seconds DESC
LIMIT 20;
```

## Python Analysis Scripts

### Complete Duration Analysis

```python
#!/usr/bin/env python3
"""
Duration analysis script for CI audit data.
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
from datetime import datetime

# Database connection
engine = create_engine('postgresql://ci_audit:password@localhost/ci_audit')

def load_duration_data():
    """Load test run duration data."""
    query = """
        SELECT
            build_id,
            pr_number,
            job_name,
            result,
            started_at,
            finished_at,
            EXTRACT(EPOCH FROM (finished_at - started_at)) / 60 as duration_minutes
        FROM test_runs
        WHERE finished_at IS NOT NULL
        ORDER BY started_at
    """
    return pd.read_sql(query, engine, parse_dates=['started_at', 'finished_at'])

def analyze_duration_statistics(df):
    """Calculate duration statistics by job type."""
    stats = df.groupby('job_name')['duration_minutes'].agg([
        'count',
        'mean',
        'median',
        'std',
        'min',
        'max',
        ('p90', lambda x: x.quantile(0.9)),
        ('p95', lambda x: x.quantile(0.95)),
        ('p99', lambda x: x.quantile(0.99))
    ]).round(2)

    print("Duration Statistics by Job Type:")
    print(stats)
    return stats

def plot_duration_trends(df):
    """Plot duration trends over time."""
    # Daily average by job type
    df['date'] = df['started_at'].dt.date
    daily_avg = df.groupby(['date', 'job_name'])['duration_minutes'].mean().reset_index()

    plt.figure(figsize=(14, 6))
    for job in daily_avg['job_name'].unique():
        job_data = daily_avg[daily_avg['job_name'] == job]
        plt.plot(job_data['date'], job_data['duration_minutes'], label=job, marker='o', markersize=3)

    plt.xlabel('Date')
    plt.ylabel('Duration (minutes)')
    plt.title('Test Duration Trends by Job Type')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.xticks(rotation=45)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('duration_trends.png', dpi=300)
    print("Saved: duration_trends.png")

def plot_duration_distribution(df):
    """Plot duration distribution box plots."""
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=df, x='job_name', y='duration_minutes')
    plt.xlabel('Job Type')
    plt.ylabel('Duration (minutes)')
    plt.title('Duration Distribution by Job Type')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig('duration_distribution.png', dpi=300)
    print("Saved: duration_distribution.png")

def plot_success_vs_failure_duration(df):
    """Compare duration of successful vs. failed runs."""
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=df, x='job_name', y='duration_minutes', hue='result')
    plt.xlabel('Job Type')
    plt.ylabel('Duration (minutes)')
    plt.title('Duration: Success vs. Failure')
    plt.xticks(rotation=45, ha='right')
    plt.legend(title='Result')
    plt.tight_layout()
    plt.savefig('duration_success_vs_failure.png', dpi=300)
    print("Saved: duration_success_vs_failure.png")

def find_outliers(df):
    """Identify duration outliers."""
    outliers = []
    for job in df['job_name'].unique():
        job_data = df[df['job_name'] == job]
        mean = job_data['duration_minutes'].mean()
        std = job_data['duration_minutes'].std()

        # Outliers: > 2 standard deviations
        job_outliers = job_data[
            abs(job_data['duration_minutes'] - mean) > 2 * std
        ].copy()

        job_outliers['std_devs'] = (job_outliers['duration_minutes'] - mean) / std
        outliers.append(job_outliers)

    outliers_df = pd.concat(outliers)
    print(f"\nFound {len(outliers_df)} outliers (>2 std devs):")
    print(outliers_df[['build_id', 'job_name', 'duration_minutes', 'std_devs']].head(10))
    return outliers_df

def main():
    """Run complete duration analysis."""
    print("Loading duration data...")
    df = load_duration_data()
    print(f"Loaded {len(df)} test runs")

    print("\n" + "="*60)
    analyze_duration_statistics(df)

    print("\n" + "="*60)
    print("Generating visualizations...")
    plot_duration_trends(df)
    plot_duration_distribution(df)
    plot_success_vs_failure_duration(df)

    print("\n" + "="*60)
    find_outliers(df)

    print("\nAnalysis complete!")

if __name__ == '__main__':
    main()
```

### Test Case Duration Analysis

```python
#!/usr/bin/env python3
"""
Test case-level duration analysis.
"""

import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import create_engine

engine = create_engine('postgresql://ci_audit:password@localhost/ci_audit')

def analyze_test_case_duration():
    """Analyze individual test case durations."""
    query = """
        SELECT
            test_suite,
            test_name,
            duration_seconds
        FROM test_cases
        WHERE duration_seconds IS NOT NULL
    """
    df = pd.read_sql(query, engine)

    # Top 20 slowest tests (by average)
    slowest = df.groupby(['test_suite', 'test_name'])['duration_seconds'].agg([
        'count', 'mean', 'median', 'max'
    ]).sort_values('mean', ascending=False).head(20)

    print("Top 20 Slowest Test Cases:")
    print(slowest)

    # Plot histogram of test durations
    plt.figure(figsize=(10, 6))
    plt.hist(df['duration_seconds'], bins=50, edgecolor='black')
    plt.xlabel('Duration (seconds)')
    plt.ylabel('Frequency')
    plt.title('Test Case Duration Distribution')
    plt.yscale('log')
    plt.tight_layout()
    plt.savefig('test_duration_histogram.png', dpi=300)
    print("Saved: test_duration_histogram.png")

if __name__ == '__main__':
    analyze_test_case_duration()
```

## Usage

```bash
# Run complete analysis
python3 scripts/analyze_duration.py

# Generate specific plots
python3 -c "
from analyze_duration import load_duration_data, plot_duration_trends
df = load_duration_data()
plot_duration_trends(df)
"
```

## Related

- [Overview](overview.md)
- [Time Series Analysis](timeseries.md)
- [Per-Suite Breakdown](per-suite.md)
