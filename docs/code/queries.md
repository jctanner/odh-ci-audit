# SQL Query Library

## Overview

Reusable SQL queries for analyzing CI audit data.

## Basic Statistics

### Record Counts

```sql
-- Count all entities
SELECT 'Pull Requests' as entity, COUNT(*) as count FROM pull_requests
UNION ALL
SELECT 'Test Runs', COUNT(*) FROM test_runs
UNION ALL
SELECT 'Test Cases', COUNT(*) FROM test_cases
UNION ALL
SELECT 'Failed Tests', COUNT(*) FROM test_cases WHERE status = 'failed';
```

### Date Range

```sql
-- Data collection period
SELECT
    MIN(created_at) as first_pr,
    MAX(created_at) as last_pr,
    MAX(created_at) - MIN(created_at) as duration
FROM pull_requests;
```

## Test Run Queries

### Success Rates

```sql
-- Overall test run success rate
SELECT
    result,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
FROM test_runs
GROUP BY result
ORDER BY count DESC;
```

### By Job Type

```sql
-- Success rate per job type
SELECT
    job_name,
    COUNT(*) as total,
    SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
    ROUND(100.0 * SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM test_runs
GROUP BY job_name
ORDER BY total DESC;
```

### Duration Analysis

```sql
-- Duration statistics by job
SELECT
    job_name,
    COUNT(*) as runs,
    ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as avg_minutes,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as median_minutes,
    ROUND(MIN(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as min_minutes,
    ROUND(MAX(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as max_minutes
FROM test_runs
WHERE finished_at IS NOT NULL
GROUP BY job_name;
```

## Test Case Queries

### Most Failing Tests

```sql
-- Top failing tests
SELECT
    test_suite,
    test_name,
    COUNT(*) as failures,
    COUNT(DISTINCT test_run_id) as affected_builds
FROM test_cases
WHERE status = 'failed'
GROUP BY test_suite, test_name
ORDER BY failures DESC
LIMIT 20;
```

### Flake Detection

```sql
-- Tests with both passes and failures
SELECT
    test_suite,
    test_name,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures,
    ROUND(100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate
FROM test_cases
GROUP BY test_suite, test_name
HAVING SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) > 0
   AND SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
   AND COUNT(*) >= 10
ORDER BY failure_rate DESC
LIMIT 20;
```

## PR Analysis

### Most Tested PRs

```sql
-- PRs with most test runs
SELECT
    pr.pr_number,
    pr.title,
    pr.author,
    COUNT(tr.id) as test_runs,
    SUM(CASE WHEN tr.result = 'FAILURE' THEN 1 ELSE 0 END) as failures
FROM pull_requests pr
JOIN test_runs tr ON pr.pr_number = tr.pr_number
GROUP BY pr.pr_number, pr.title, pr.author
ORDER BY test_runs DESC
LIMIT 20;
```

### PRs with Most Failures

```sql
-- PRs with highest failure counts
SELECT
    pr.pr_number,
    pr.title,
    COUNT(DISTINCT tc.id) as failed_tests,
    COUNT(DISTINCT tr.id) as failed_runs
FROM pull_requests pr
JOIN test_runs tr ON pr.pr_number = tr.pr_number
JOIN test_cases tc ON tr.id = tc.test_run_id
WHERE tc.status = 'failed'
GROUP BY pr.pr_number, pr.title
ORDER BY failed_tests DESC
LIMIT 20;
```

## Time Series

### Daily Statistics

```sql
-- Daily test run statistics
SELECT
    DATE(started_at) as date,
    COUNT(*) as total_runs,
    SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
    SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) as failures,
    ROUND(100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate
FROM test_runs
GROUP BY DATE(started_at)
ORDER BY date;
```

### Weekly Trends

```sql
-- Weekly trends
SELECT
    DATE_TRUNC('week', started_at) as week,
    COUNT(*) as total_runs,
    ROUND(100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate,
    ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 2) as avg_duration_minutes
FROM test_runs
WHERE finished_at IS NOT NULL
GROUP BY week
ORDER BY week;
```

## Failure Classification

### By Type

```sql
-- Failure type distribution
SELECT
    failure_type,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
FROM test_cases
WHERE status = 'failed' AND failure_type IS NOT NULL
GROUP BY failure_type
ORDER BY count DESC;
```

## Related

- [Duration Analysis Code](../analysis/duration/code.md)
- [Failure Analysis Code](../analysis/failures/code.md)
- [Database Schema](../setup/database-schema.md)
