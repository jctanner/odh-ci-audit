# Flake Rate Analysis

## Overview

Analysis of test flakiness - tests that pass and fail on identical code.

## Overall Flake Rate

```sql
-- Global flake metrics
WITH flaky_tests AS (
    SELECT
        test_name,
        COUNT(*) as total,
        SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
    FROM test_cases
    GROUP BY test_name
    HAVING SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) > 0
       AND SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
)
SELECT
    COUNT(*) as flaky_tests,
    SUM(failures) as total_flake_failures,
    ROUND(AVG(100.0 * failures / total), 2) as avg_flake_rate
FROM flaky_tests;
```

**Results**:

- **Total Flaky Tests**: 435 unique tests (tests that both pass and fail)
- **Total Failures from Flakes**: 38,973 failures
- **Percentage of All Failures**: 99.6% (38,973 out of 39,117 total failures)
- **Average Flake Rate**: 21.9% (avg failure rate across flaky tests)

**Critical Finding**: Nearly ALL failures (99.6%) are from flaky tests, not consistent failures. This indicates that the CI system suffers primarily from non-deterministic test behavior rather than broken code. Only 144 failures (0.4%) are from consistently failing tests.

## Top Flaky Tests

**Top 10 Flakiest Tests** (sorted by failure rate):

| Test | Executions | Passes | Failures | Failure Rate |
|------|-----------|--------|----------|--------------|
| cluster install: install should succeed: overall | 405 | 33 | 372 | **91.9%** |
| TestOdhOperator/services/gateway | 24 | 2 | 22 | **91.7%** |
| operator conditions (multiple) | 11 each | 1 each | 10 each | **90.9%** |
| **TestOdhOperator** | 5,373 | 995 | 4,378 | **81.5%** |
| cluster install: install should succeed: other | 401 | 29 | 372 | **92.8%** |
| TestOdhOperator/services/group_1 | 2,439 | 854 | 1,585 | 65.0% |
| Run...opendatahub-operator-e2e-e2e... | 3,489 | 1,239 | 2,250 | 64.5% |
| TestOdhOperator/services | 2,803 | 1,050 | 1,753 | 62.5% |
| TestOdhOperator/services/group_1/monitoring | 2,308 | 909 | 1,399 | 60.6% |
| TestOdhOperator/components | 3,174 | 1,431 | 1,743 | 54.9% |

**Insights**:
- Cluster install tests have >90% flake rates (infrastructure issues)
- **TestOdhOperator** has 81.5% flake rate with 4,378 failures - the primary CI problem
- Multiple operator condition checks fail at 90.9% rate
- Most flaky tests are e2e tests, indicating environment/timing issues

## Flake Trends

### Weekly Failure Rate Over Time

![Weekly Failure Rate](../images/weekly_failure_rate.png)

**Analysis**: The weekly failure rate visualization shows both stacked area and line charts of test run results over time. The data reveals:

- Success rates (green) generally dominate but fluctuate significantly week-to-week
- Failure rates (red) show spikes correlating with specific periods
- Aborted runs (gray) represent a consistent portion of total runs
- High variability indicates environmental or infrastructure instability rather than consistent code issues

## Test Flakes vs. Infrastructure Flakes: Understanding the Distinction

This analysis shows **99.6% of failures are from flaky tests** (tests that sometimes pass, sometimes fail). A critical follow-up question is: **WHY are the tests flaky?**

### Root Cause Breakdown

From [Common Failures](common-failures.md) failure type analysis by examining build logs:

| Root Cause | % of Failures | What This Means |
|------------|---------------|-----------------|
| **Infrastructure Issues** | **87.6%** | Timeouts, image pulls, network errors, pod startup failures |
| Configuration Issues | 12.3% | YAML parsing, permissions, missing config |
| Code Regressions | 0.1% | Panics, nil pointers, assertion failures |
| Unknown/Other | 0.1% | Unclassified errors |

### What This Tells Us

**The tests ARE flaky (99.6% stat), AND the root cause is primarily infrastructure (87.6% stat).**

Breaking it down:

1. **Infrastructure-Caused Test Flakes: ~88% of all failures**
   - Tests fail due to timeouts, image pull errors, network issues, pod startup problems
   - The **test code itself is often fine**, but infrastructure makes it flaky
   - Same test, same code → sometimes passes (good infra), sometimes fails (degraded infra)
   - Example: TestOdhOperator (81.5% flake rate) fails mostly due to operator pods not starting in time

2. **Test-Design Flakes: ~12% of all failures**
   - Tests with inherent race conditions, timing dependencies, or poor cleanup
   - Would flake even on perfect infrastructure
   - Require test code fixes, not infrastructure improvements

3. **Actual Code Bugs Caught: ~0.1% of all failures**
   - Real code regressions (panics, nil pointers) that tests legitimately caught
   - This is what CI **should** be catching, but it's drowned out by noise

### Key Insight

**The CI system's 99.6% flake rate is NOT primarily a test quality problem** - it's an infrastructure reliability problem. The tests themselves are mostly well-written, but they're running in an environment where:
- Infrastructure fails 88% of the time tests fail
- Time-of-day affects success rates by 21% (peak vs. off-peak hours)
- Same code on same SHA produces different results 63% of the time ([Same-SHA Analysis](same-sha-analysis.md))

### Implications

1. **Fixing flaky tests won't help much if infrastructure isn't fixed**
   - You could rewrite all 435 flaky tests to be perfect
   - They'd still fail 88% of the time due to timeouts, image pulls, network issues

2. **Fixing infrastructure won't eliminate all flakes**
   - ~12% of flakes are test-design issues
   - But it would reduce the flake problem by 7-8x

3. **The 0.1% signal is lost in 99.9% noise**
   - CI is failing to serve its primary purpose: catching bugs
   - Developers can't trust test failures as indicators of code problems

### Related Analysis

- [Infrastructure Issues](infrastructure.md) - 87.6% of failures show infrastructure error patterns
- [Same-SHA Analysis](same-sha-analysis.md) - 95% of failures aren't code issues
- [Common Failures](common-failures.md) - Failure type distribution breakdown

## Impact Metrics

From [Time Cost Analysis](time-cost.md) and [Same-SHA Analysis](same-sha-analysis.md):

- **Developer time wasted**: 529 hours blocked by test failures (10% of 5,287 hours failed runs)
- **Manual retry commands**: ~3,005 `/retest` commands issued across 6 months
- **PRs requiring retries**: 75.4% of all PRs (627 out of 832)
- **Average retries per PR**: 4.8 manual retry commands
- **PRs delayed by flakes**: 63.1% experienced same-SHA flakes (identical code failing)

## Related

- [Test Flakes](../analysis/failure-types/02-flakes.md)
- [Per-Test Breakdown](../analysis/failures/per-test.md)
