# Failure Analysis - Per-Test Breakdown

## Overview

Identify which specific tests fail most frequently and understand their failure patterns.

## Queries

### Most Frequently Failing Tests

```sql
-- Top 20 tests by failure count
SELECT
    test_suite,
    test_name,
    COUNT(*) as total_executions,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures,
    SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes,
    ROUND(100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate
FROM test_cases
GROUP BY test_suite, test_name
HAVING SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
ORDER BY failures DESC
LIMIT 20;
```

### Flakiest Tests

```sql
-- Tests with highest flake rate (both passes and failures)
SELECT
    test_suite,
    test_name,
    COUNT(*) as total_executions,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures,
    SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes,
    ROUND(100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate
FROM test_cases
GROUP BY test_suite, test_name
HAVING SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
   AND SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) > 0
   AND COUNT(*) >= 10  -- At least 10 executions
ORDER BY failure_rate DESC, failures DESC
LIMIT 20;
```

### Test Failure Reasons

```sql
-- Group failures by test and failure message
SELECT
    test_suite,
    test_name,
    failure_message,
    COUNT(*) as occurrences
FROM test_cases
WHERE status = 'failed'
GROUP BY test_suite, test_name, failure_message
ORDER BY occurrences DESC
LIMIT 50;
```

### Tests That Never Fail

```sql
-- Most reliable tests
SELECT
    test_suite,
    test_name,
    COUNT(*) as total_executions
FROM test_cases
WHERE test_suite IS NOT NULL
GROUP BY test_suite, test_name
HAVING SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) = 0
   AND COUNT(*) >= 10
ORDER BY total_executions DESC
LIMIT 20;
```

## Failure Type by Test

```sql
-- Breakdown of failure types for each test
SELECT
    tc.test_suite,
    tc.test_name,
    tc.failure_type,
    COUNT(*) as count
FROM test_cases tc
WHERE tc.status = 'failed'
  AND tc.failure_type IS NOT NULL
GROUP BY tc.test_suite, tc.test_name, tc.failure_type
ORDER BY tc.test_suite, tc.test_name, count DESC;
```

## Python Analysis

```python
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine

engine = create_engine('postgresql://ci_audit:password@localhost/ci_audit')

def analyze_test_failures():
    """Analyze test-level failures."""
    query = """
        SELECT
            test_suite,
            test_name,
            status,
            COUNT(*) as count
        FROM test_cases
        GROUP BY test_suite, test_name, status
    """
    df = pd.read_sql(query, engine)

    # Pivot to get failures and passes per test
    pivot = df.pivot_table(
        index=['test_suite', 'test_name'],
        columns='status',
        values='count',
        fill_value=0
    ).reset_index()

    # Calculate failure rate
    pivot['total'] = pivot.get('failed', 0) + pivot.get('passed', 0) + pivot.get('skipped', 0)
    pivot['failure_rate'] = 100.0 * pivot.get('failed', 0) / pivot['total']

    # Top 20 by failure count
    top_failures = pivot.nlargest(20, 'failed')
    print("Top 20 Tests by Failure Count:")
    print(top_failures[['test_suite', 'test_name', 'failed', 'passed', 'failure_rate']])

    # Flakiest tests (non-zero pass and fail)
    flaky = pivot[(pivot.get('failed', 0) > 0) & (pivot.get('passed', 0) > 0)]
    top_flaky = flaky.nlargest(20, 'failure_rate')
    print("\nTop 20 Flakiest Tests:")
    print(top_flaky[['test_suite', 'test_name', 'failed', 'passed', 'failure_rate']])

    return pivot

def plot_failure_distribution():
    """Plot distribution of test failure rates."""
    query = """
        SELECT
            test_suite,
            test_name,
            100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*) as failure_rate
        FROM test_cases
        GROUP BY test_suite, test_name
        HAVING COUNT(*) >= 5
    """
    df = pd.read_sql(query, engine)

    plt.figure(figsize=(10, 6))
    plt.hist(df['failure_rate'], bins=50, edgecolor='black')
    plt.xlabel('Failure Rate (%)')
    plt.ylabel('Number of Tests')
    plt.title('Distribution of Test Failure Rates')
    plt.tight_layout()
    plt.savefig('test_failure_distribution.png', dpi=300)
    print("Saved: test_failure_distribution.png")

def plot_top_failing_tests():
    """Bar chart of top failing tests."""
    query = """
        SELECT
            test_suite || '.' || test_name as full_test_name,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
        FROM test_cases
        GROUP BY test_suite, test_name
        ORDER BY failures DESC
        LIMIT 15
    """
    df = pd.read_sql(query, engine)

    plt.figure(figsize=(12, 8))
    plt.barh(df['full_test_name'], df['failures'])
    plt.xlabel('Number of Failures')
    plt.ylabel('Test Name')
    plt.title('Top 15 Failing Tests')
    plt.tight_layout()
    plt.savefig('top_failing_tests.png', dpi=300)
    print("Saved: top_failing_tests.png")

if __name__ == '__main__':
    analyze_test_failures()
    plot_failure_distribution()
    plot_top_failing_tests()
```

## Test Stability Score

Calculate stability metric for each test:

```python
def calculate_stability_score(passes, failures):
    """
    Stability score: 0-100, where:
    - 100 = always passes
    - 0 = always fails
    - 50 = 50% pass rate (very flaky)
    """
    total = passes + failures
    if total == 0:
        return None
    return 100.0 * passes / total

# Apply to dataframe
df['stability_score'] = df.apply(
    lambda row: calculate_stability_score(row['passed'], row['failed']),
    axis=1
)

# Tests with stability 40-60% are highly flaky
flaky = df[(df['stability_score'] >= 40) & (df['stability_score'] <= 60)]
```

## Test Execution Frequency

```sql
-- How often is each test executed?
SELECT
    test_suite,
    test_name,
    COUNT(*) as executions,
    COUNT(DISTINCT test_run_id) as unique_builds,
    MIN(collected_at) as first_seen,
    MAX(collected_at) as last_seen
FROM test_cases
GROUP BY test_suite, test_name
ORDER BY executions DESC;
```

## Findings

From [Common Failures](../../findings/common-failures.md) and [Flake Rate Analysis](../../findings/flake-rate.md):

### Top 5-10 Tests Account for Majority of Failures

**CONFIRMED - Top 10 tests account for 16,799 failures (42.9% of all 39,117 failures)**:

| Test | Executions | Failures | Passes | Failure Rate | % of All Failures |
|------|-----------|----------|--------|--------------|-------------------|
| **TestOdhOperator** | 5,373 | **4,378** | 995 | **81.5%** | **11.2%** |
| Run multi-stage test test phase | 8,157 | 2,905 | 5,252 | 35.6% | 7.4% |
| Run...opendatahub-operator-e2e... | 3,489 | 2,250 | 1,239 | 64.5% | 5.8% |
| Clone the correct source code... | 20,486 | 2,164 | 18,322 | 10.6% | 5.5% |
| TestOdhOperator/services | 2,803 | 1,753 | 1,050 | 62.5% | 4.5% |
| TestOdhOperator/components | 3,174 | 1,743 | 1,431 | 54.9% | 4.5% |
| TestOdhOperator/services/group_1 | 2,439 | 1,585 | 854 | 65.0% | 4.1% |
| TestOdhOperator/services/group_1/monitoring | 2,308 | 1,399 | 909 | 60.6% | 3.6% |
| Build image opendatahub-operator... | 17,830 | 1,246 | 16,584 | 7.0% | 3.2% |
| Run multi-stage test pre phase | 9,270 | 1,113 | 8,157 | 12.0% | 2.8% |

**Critical Finding**: **TestOdhOperator alone represents 11.2% of ALL test failures** (4,378 out of 39,117). This single test is the primary driver of CI unreliability.

### Flakiest Tests - Highest Failure Rates

From [Flake Rate Analysis](../../findings/flake-rate.md), tests with both passes AND failures (flaky tests):

| Test | Executions | Passes | Failures | Failure Rate | Classification |
|------|-----------|--------|----------|--------------|----------------|
| cluster install: install should succeed: overall | 405 | 33 | 372 | **91.9%** | Infrastructure (cluster provisioning) |
| TestOdhOperator/services/gateway | 24 | 2 | 22 | **91.7%** | Infrastructure |
| operator conditions (multiple tests) | 11 each | 1 each | 10 each | **90.9%** | Infrastructure (operator not ready) |
| **TestOdhOperator** | 5,373 | 995 | 4,378 | **81.5%** | Infrastructure |
| cluster install: install should succeed: other | 401 | 29 | 372 | **92.8%** | Infrastructure (cluster provisioning) |
| TestOdhOperator/services/group_1 | 2,439 | 854 | 1,585 | 65.0% | Infrastructure |
| Run...opendatahub-operator-e2e... | 3,489 | 1,239 | 2,250 | 64.5% | Infrastructure |
| TestOdhOperator/services | 2,803 | 1,050 | 1,753 | 62.5% | Infrastructure |
| TestOdhOperator/services/group_1/monitoring | 2,308 | 909 | 1,399 | 60.6% | Infrastructure |
| TestOdhOperator/components | 3,174 | 1,431 | 1,743 | 54.9% | Infrastructure |

**Key Insights**:
- **Cluster install tests**: 91-93% flake rates - infrastructure provisioning issues
- **TestOdhOperator hierarchy**: Parent test (81.5%) and all child tests (60-65%) are highly flaky
- **Operator condition checks**: 90.9% flake rate - operators not reporting status in time
- **ALL top flaky tests are infrastructure-related**, not test design flaws

### Component-Specific Insights

From [Common Failures](../../findings/common-failures.md) component analysis:

**NOT Dashboard/KServe/DSP as expected - they're actually the MOST RELIABLE**:

| Component | Total Tests | Failures | Failure Rate | Reality vs Expectation |
|-----------|-------------|----------|--------------|------------------------|
| **Dashboard** | 51,379 | 295 | **0.6%** | **Most reliable** (expected flaky) |
| **DataSciencePipelines** | 118,831 | 710 | **0.6%** | **Most reliable** (expected flaky) |
| **KServe** | 41,108 | 658 | **1.6%** | **Very reliable** (expected flaky) |
| **ModelRegistry** | 35,708 | 243 | **0.7%** | Very reliable |
| Kueue | 40,982 | 846 | 2.1% | Reliable |
| Monitoring | 81,772 | 3,151 | 3.9% | Moderate |
| Gateway | 10,111 | 527 | 5.2% | Moderate |
| **Trainer** | 19,428 | 1,904 | **9.8%** | **Least reliable** |

**Surprising Finding**: Dashboard, KServe, and DSP are among the MOST reliable components (0.6-1.6% failure rates). Trainer is the least reliable (9.8%).

**100% Failure Rate Pattern**:

All failing tests in Dashboard, KServe, and DSP components show **100% failure rate** when they fail, suggesting:
- Tests are deterministically broken or disabled
- Not experiencing intermittent failures (not flaky in the traditional sense)
- Likely test infrastructure setup issues

### Infrastructure-Related Tests Have Higher Failure Rates

**CONFIRMED**:

Tests that interact heavily with infrastructure show highest failure rates:

| Test Category | Example Tests | Failure Rate | Root Cause |
|---------------|---------------|--------------|------------|
| **Cluster install** | install should succeed | **91-93%** | Infrastructure provisioning timeouts |
| **Operator status checks** | operator conditions | **90.9%** | Operators not ready in time |
| **E2E integration** | TestOdhOperator | **81.5%** | Pod startup, timeouts, network |
| **Service tests** | services/gateway, services/monitoring | **60-92%** | Service mesh, networking |
| **Component tests** | components/* | **55-65%** | Component operators not ready |

**Build/validation tests** (low infrastructure dependency):

| Test Category | Example Tests | Failure Rate | Root Cause |
|---------------|---------------|--------------|------------|
| **Code builds** | Build image opendatahub-operator | **7.0%** | Efficient, minimal infrastructure |
| **Source clone** | Clone the correct source code | **10.6%** | Network/git issues (still infra) |
| **Test setup** | Run multi-stage test pre phase | **12.0%** | Setup issues |

**Conclusion**: Tests with heavy infrastructure dependencies (operator status, pod readiness, service mesh) have **6-13x higher failure rates** than build/validation tests.

### Some Tests Are Consistently Broken

**PARTIALLY CONFIRMED - but pattern is opposite of expectation**:

From [Common Failures](../../findings/common-failures.md):

**Tests with 100% failure rate** (all attempts fail):
- Dashboard component tests: 109 failures, 0 passes (100% failure)
- KServe component tests: 254 failures, 0 passes (100% failure)
- DataSciencePipelines component tests: 99 failures, 0 passes (100% failure)

**However**:
- These represent a SMALL minority of total failures
- Most failures (99.6%) are from FLAKY tests (tests that both pass and fail)
- Only 144 failures (0.4%) are from consistently failing tests

**Flaky Tests Dominate**:

From [Flake Rate Analysis](../../findings/flake-rate.md):
- **435 unique flaky tests** (tests with both passes and failures)
- **38,973 failures from flaky tests** (99.6% of all failures)
- **144 failures from consistently failing tests** (0.4% of all failures)

**Conclusion**: The CI system's problem is NOT consistently broken tests - it's **non-deterministic flakiness** where tests pass sometimes and fail other times on identical code.

### Most Reliable Tests (Never Fail)

While not explicitly measured in the dataset, we can infer from component data:

From [Common Failures](../../findings/common-failures.md), components with <1% failure rates have many reliable tests:
- **Dashboard**: 51,084 passing tests (99.4% of executions)
- **DataSciencePipelines**: 118,121 passing tests (99.4% of executions)
- **ModelRegistry**: 35,465 passing tests (99.3% of executions)

**Estimated**: Thousands of test cases have 0% failure rates across these reliable components.

### Failure Type by Test

From [Common Failures](../../findings/common-failures.md), the only specific failure message in top 20:

| Failure Message | Occurrences | Affected Tests | Type |
|-----------------|-------------|----------------|------|
| **Operator unavailable (null): operator is not reporting conditions** | **330** | **34** | Infrastructure/Dependency |

**All other top failure messages** are generic "Test X failed" without specific error details, making root cause analysis difficult without examining build logs.

This is why the **87.6% infrastructure categorization** required build log analysis - test case failure messages alone don't reveal the infrastructure root causes.

## Related

- [Overview](overview.md)
- [Classification](classification.md)
- [Time Series](timeseries.md)
- [SQL & Python](code.md)
