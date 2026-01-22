# Failure Analysis - SQL & Python

## Complete SQL Query Library

### Overall Failure Statistics

```sql
-- Test run failure rates
SELECT
    result,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
FROM test_runs
GROUP BY result
ORDER BY count DESC;

-- Test case failure rates
SELECT
    status,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
FROM test_cases
GROUP BY status
ORDER BY count DESC;
```

### Failure Rate by Job Type

```sql
-- Job-level failure analysis
SELECT
    job_name,
    COUNT(*) as total_runs,
    SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
    SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) as failures,
    SUM(CASE WHEN result = 'ABORTED' THEN 1 ELSE 0 END) as aborted,
    ROUND(100.0 * SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate,
    ROUND(100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate,
    ROUND(100.0 * SUM(CASE WHEN result = 'ABORTED' THEN 1 ELSE 0 END) / COUNT(*), 2) as abort_rate
FROM test_runs
GROUP BY job_name
ORDER BY total_runs DESC;
```

### Failure Type Distribution

```sql
-- Breakdown by failure classification
SELECT
    failure_type,
    COUNT(*) as failures,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage,
    COUNT(DISTINCT test_name) as unique_tests,
    COUNT(DISTINCT test_run_id) as unique_builds
FROM test_cases
WHERE status = 'failed'
  AND failure_type IS NOT NULL
GROUP BY failure_type
ORDER BY failures DESC;
```

### Flake Detection Query

```sql
-- Comprehensive flake analysis
WITH test_stats AS (
    SELECT
        test_suite,
        test_name,
        COUNT(*) as total_executions,
        SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures,
        SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped
    FROM test_cases
    GROUP BY test_suite, test_name
)
SELECT
    test_suite,
    test_name,
    total_executions,
    passes,
    failures,
    skipped,
    ROUND(100.0 * failures / total_executions, 2) as failure_rate,
    ROUND(100.0 * passes / total_executions, 2) as pass_rate,
    -- Flake score: entropy-based measure of inconsistency
    ROUND(
        -1 * (
            (passes::float / total_executions) * LOG(passes::float / total_executions + 0.0001) +
            (failures::float / total_executions) * LOG(failures::float / total_executions + 0.0001)
        ),
        3
    ) as flake_score
FROM test_stats
WHERE failures > 0
  AND passes > 0
  AND total_executions >= 10
ORDER BY flake_score DESC, failures DESC
LIMIT 50;
```

### Most Common Failure Messages

```sql
-- Top failure messages
SELECT
    LEFT(failure_message, 100) as message_preview,
    COUNT(*) as occurrences,
    COUNT(DISTINCT test_name) as affected_tests,
    COUNT(DISTINCT test_run_id) as affected_builds
FROM test_cases
WHERE status = 'failed'
  AND failure_message IS NOT NULL
GROUP BY LEFT(failure_message, 100)
ORDER BY occurrences DESC
LIMIT 30;
```

### PR-Level Failure Analysis

```sql
-- PRs with highest failure counts
SELECT
    pr.pr_number,
    pr.title,
    pr.author,
    COUNT(DISTINCT tr.id) as total_runs,
    SUM(CASE WHEN tr.result = 'FAILURE' THEN 1 ELSE 0 END) as failed_runs,
    SUM(CASE WHEN tc.status = 'failed' THEN 1 ELSE 0 END) as failed_tests
FROM pull_requests pr
JOIN test_runs tr ON pr.pr_number = tr.pr_number
LEFT JOIN test_cases tc ON tr.id = tc.test_run_id
GROUP BY pr.pr_number, pr.title, pr.author
HAVING SUM(CASE WHEN tr.result = 'FAILURE' THEN 1 ELSE 0 END) > 0
ORDER BY failed_runs DESC, failed_tests DESC
LIMIT 20;
```

### Time-Based Failure Analysis

```sql
-- Failure patterns by day of week
SELECT
    EXTRACT(DOW FROM started_at) as day_of_week,
    CASE EXTRACT(DOW FROM started_at)
        WHEN 0 THEN 'Sunday'
        WHEN 1 THEN 'Monday'
        WHEN 2 THEN 'Tuesday'
        WHEN 3 THEN 'Wednesday'
        WHEN 4 THEN 'Thursday'
        WHEN 5 THEN 'Friday'
        WHEN 6 THEN 'Saturday'
    END as day_name,
    COUNT(*) as total_runs,
    SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) as failures,
    ROUND(100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate
FROM test_runs
GROUP BY EXTRACT(DOW FROM started_at)
ORDER BY day_of_week;
```

## Complete Python Analysis Script

```python
#!/usr/bin/env python3
"""
Complete failure analysis script for CI audit data.
"""

import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
from collections import defaultdict

# Database connection
engine = create_engine('postgresql://ci_audit:password@localhost/ci_audit')

# Failure classification patterns
PATTERNS = {
    'infrastructure': [
        r'timeout waiting for pod',
        r'image pull.*failed',
        r'context deadline exceeded',
        r'connection refused',
        r'no space left on device',
        r'failed to pull image',
        r'node not found',
        r'insufficient.*resources',
    ],
    'flake': [
        r'Eventually timed out',
        r'Consistently',
        r'race detected',
        r'timeout.*waiting',
        r'flake',
    ],
    'regression': [
        r'Expected.*but got',
        r'panic:',
        r'nil pointer dereference',
        r'assertion failed',
        r'test.*failed',
    ],
    'configuration': [
        r'invalid.*yaml',
        r'permission denied',
        r'forbidden',
        r'missing.*config',
        r'invalid configuration',
    ],
    'dependency': [
        r'crd.*not found',
        r'no matches for kind',
        r'operator.*not found',
        r'webhook.*failed',
        r'api version.*not found',
    ],
    'environment': [
        r'quota.*exceeded',
        r'already exists',
        r'cluster.*unstable',
        r'pvc.*failed',
    ],
}

def classify_failure(failure_message, stacktrace=''):
    """Classify failure based on message and stacktrace."""
    if not failure_message:
        return 'unknown'

    text = f"{failure_message} {stacktrace}".lower()

    for category, patterns in PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return category

    return 'unknown'

def load_failures():
    """Load all failed test cases."""
    query = """
        SELECT
            tc.id,
            tc.test_run_id,
            tc.test_suite,
            tc.test_name,
            tc.failure_message,
            tc.stacktrace,
            tr.job_name,
            tr.pr_number,
            tr.started_at
        FROM test_cases tc
        JOIN test_runs tr ON tc.test_run_id = tr.id
        WHERE tc.status = 'failed'
    """
    return pd.read_sql(query, engine, parse_dates=['started_at'])

def classify_all_failures(df):
    """Apply classification to all failures."""
    df['failure_type'] = df.apply(
        lambda row: classify_failure(row['failure_message'], row['stacktrace']),
        axis=1
    )
    return df

def analyze_failure_distribution(df):
    """Analyze distribution of failure types."""
    distribution = df['failure_type'].value_counts()
    percentages = 100.0 * distribution / len(df)

    print("Failure Type Distribution:")
    print("=" * 60)
    for ftype, count in distribution.items():
        pct = percentages[ftype]
        print(f"{ftype:20s}: {count:5d} ({pct:5.2f}%)")
    print("=" * 60)
    print(f"{'TOTAL':20s}: {len(df):5d} (100.00%)")

    return distribution

def plot_failure_types(df):
    """Plot failure type distribution."""
    distribution = df['failure_type'].value_counts()

    plt.figure(figsize=(10, 6))
    distribution.plot(kind='bar', color='steelblue', edgecolor='black')
    plt.xlabel('Failure Type')
    plt.ylabel('Number of Failures')
    plt.title('Distribution of Failure Types')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig('failure_type_distribution.png', dpi=300)
    print("Saved: failure_type_distribution.png")

def analyze_flakes():
    """Identify flaky tests."""
    query = """
        SELECT
            test_suite,
            test_name,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
        FROM test_cases
        GROUP BY test_suite, test_name
        HAVING SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) > 0
           AND SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
           AND COUNT(*) >= 10
    """
    df = pd.read_sql(query, engine)
    df['failure_rate'] = 100.0 * df['failures'] / df['total']
    df = df.sort_values('failure_rate', ascending=False)

    print("\nTop 20 Flakiest Tests:")
    print("=" * 80)
    print(df.head(20).to_string(index=False))

    return df

def plot_failure_timeline(df):
    """Plot failures over time by type."""
    df['date'] = df['started_at'].dt.date
    timeline = df.groupby(['date', 'failure_type']).size().reset_index(name='count')
    pivot = timeline.pivot(index='date', columns='failure_type', values='count').fillna(0)

    plt.figure(figsize=(14, 6))
    pivot.plot.area(stacked=True, alpha=0.7, ax=plt.gca())
    plt.xlabel('Date')
    plt.ylabel('Number of Failures')
    plt.title('Failures Over Time by Type')
    plt.legend(title='Failure Type', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig('failure_timeline.png', dpi=300)
    print("Saved: failure_timeline.png")

def main():
    """Run complete failure analysis."""
    print("Loading failure data...")
    df = load_failures()
    print(f"Loaded {len(df)} failed test cases")

    print("\n" + "="*60)
    print("Classifying failures...")
    df = classify_all_failures(df)

    print("\n" + "="*60)
    analyze_failure_distribution(df)

    print("\n" + "="*60)
    print("Generating visualizations...")
    plot_failure_types(df)
    plot_failure_timeline(df)

    print("\n" + "="*60)
    analyze_flakes()

    print("\nAnalysis complete!")

if __name__ == '__main__':
    main()
```

## Usage

```bash
# Run complete analysis
python3 scripts/analyze_failures.py

# Export failures to CSV
psql -U ci_audit -d ci_audit -c \
  "COPY (SELECT * FROM test_cases WHERE status='failed') TO STDOUT CSV HEADER" \
  > failures.csv

# Classify and update database
python3 scripts/classify_failures.py --update-db
```

## Related

- [Overview](overview.md)
- [Classification](classification.md)
- [Time Series](timeseries.md)
- [Per-Test Breakdown](per-test.md)
