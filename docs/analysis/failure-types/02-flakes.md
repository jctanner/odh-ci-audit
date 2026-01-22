# Test Flakes

## Definition

Tests that fail intermittently without code changes. Pass on retry or on same commit in different runs.

## Characteristics

- Same test passes and fails on identical code
- Often timing-related
- Race conditions
- Eventually/Consistently timeout errors
- Non-deterministic behavior

## Detection

### Pattern Matching

```python
FLAKE_PATTERNS = [
    r'Eventually timed out',
    r'Consistently',
    r'race detected',
    r'timeout.*waiting',
    r'flake',
    r'timed out after',
]
```

### Statistical Detection

```sql
-- Tests that both pass and fail
SELECT
    test_name,
    passes,
    failures,
    100.0 * failures / (passes + failures) as flake_rate
FROM (
    SELECT
        test_name,
        SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
    FROM test_cases
    GROUP BY test_name
) t
WHERE passes > 0 AND failures > 0
ORDER BY flake_rate DESC;
```

## Statistics

From [Flake Rate Analysis](../../findings/flake-rate.md) of test execution data:

**Overall Flake Metrics**:

- **Total Flaky Tests**: 435 unique tests (tests that both pass and fail)
- **Total Failures from Flakes**: 38,973 failures
- **Percentage of All Failures**: **99.6%** (38,973 out of 39,117 total failures)
- **Average Flake Rate**: 21.9% (average failure rate across flaky tests)
- **Consistently Failing Tests**: Only 144 failures (0.4%) are from tests that never pass

**Critical Finding**: Nearly ALL failures (99.6%) come from flaky tests rather than consistently broken tests. This indicates the CI system suffers from non-deterministic test behavior, not broken code.

**Root Cause Breakdown** (from [Common Failures](../../findings/common-failures.md)):

| Root Cause | % of Failures | What This Means |
|------------|---------------|-----------------|
| **Infrastructure Issues** | **87.6%** | Timeouts, image pulls, network errors, pod startup failures cause test flakes |
| Configuration Issues | 12.3% | YAML parsing, permissions, missing config |
| Code Regressions | 0.1% | Panics, nil pointers, assertion failures - actual bugs caught |
| Unknown/Other | 0.1% | Unclassified errors |

**Key Insight**: The tests ARE flaky (99.6%), AND the root cause is primarily infrastructure (87.6%). Infrastructure failures make tests flaky - the test code itself is often fine.

## Common Causes

### Timing Issues

```go
// Anti-pattern: Hard-coded timeouts
time.Sleep(5 * time.Second)
if !pod.Ready {
    return errors.New("pod not ready")
}

// Better: Use Eventually with reasonable timeout
Eventually(func() bool {
    return pod.Ready
}, timeout, interval).Should(BeTrue())
```

### Race Conditions

- Concurrent resource updates
- Ordering dependencies between tests
- Shared test state

### Resource Contention

- Test cluster resource limits
- Multiple tests competing for resources
- Namespace/resource name conflicts

### External Dependencies

- Network latency variability
- Third-party service availability
- Container registry responsiveness

## Impact

- Developer frustration
- Reduced CI signal-to-noise ratio
- "/retest" spam in PRs
- Delayed merges
- Loss of confidence in tests

## Top Flaky Tests

From [Flake Rate Analysis](../../findings/flake-rate.md), **Top 10 Flakiest Tests** (sorted by failure rate):

| Test | Executions | Passes | Failures | Failure Rate |
|------|-----------|--------|----------|--------------|
| cluster install: install should succeed: overall | 405 | 33 | 372 | **91.9%** |
| TestOdhOperator/services/gateway | 24 | 2 | 22 | **91.7%** |
| operator conditions (multiple tests) | 11 each | 1 each | 10 each | **90.9%** |
| **TestOdhOperator** | **5,373** | **995** | **4,378** | **81.5%** |
| cluster install: install should succeed: other | 401 | 29 | 372 | **92.8%** |
| TestOdhOperator/services/group_1 | 2,439 | 854 | 1,585 | 65.0% |
| Run...opendatahub-operator-e2e-e2e... | 3,489 | 1,239 | 2,250 | 64.5% |
| TestOdhOperator/services | 2,803 | 1,050 | 1,753 | 62.5% |
| TestOdhOperator/services/group_1/monitoring | 2,308 | 909 | 1,399 | 60.6% |
| TestOdhOperator/components | 3,174 | 1,431 | 1,743 | 54.9% |

**Analysis**:

- **Cluster install tests have >90% flake rates** - These are infrastructure provisioning issues, not test bugs
- **TestOdhOperator is the primary problem** - 81.5% flake rate with 4,378 failures (11.2% of ALL failures)
- **Multiple operator condition checks fail at 90.9%** - Operators not reporting status in time
- **Most flaky tests are e2e tests** - Indicates environment/timing/infrastructure issues rather than test design problems

**Same-SHA Evidence** (from [Same-SHA Analysis](../../findings/same-sha-analysis.md)):

- **1,527 PR+SHA combinations** had identical code produce both pass and fail results
- **63.1% of PRs** (525 out of 832) experienced same-SHA flakes
- **46.2% of flakes** succeeded first, then failed later - proves infrastructure degradation over time
- **75.4% of PRs** required manual `/retest` commands
- **Average 4.8 retry commands per PR**
- **~3,005 total `/retest` or `/test` commands** issued in 6-month period

This definitively proves that **~95% of failures are infrastructure/test flakiness, not code issues**.

## Mitigation Strategies

### Code Improvements

1. **Increase timeouts appropriately**
   ```go
   const (
       timeout  = time.Minute * 5  // Not 30 seconds
       interval = time.Second * 10
   )
   ```

2. **Use Eventually/Consistently correctly**
   ```go
   Eventually(checkPodReady, timeout, interval).Should(Succeed())
   Consistently(checkPodRunning, duration, interval).Should(Succeed())
   ```

3. **Avoid sleep, use polling**

4. **Isolate test state** - unique namespaces, resource names

5. **Add retries for transient operations**

### CI Improvements

1. Retry flaky tests automatically (Ginkgo `--flake-attempts`)
2. Track flake rates in metrics
3. Quarantine consistently flaky tests
4. Allocate more resources to test cluster

### Process

1. Label flaky tests in code
2. Create tracking issues for flakes
3. Prioritize flake fixes
4. Review new tests for flake potential

## Query for Analysis

```sql
-- Flake rate by test over time
SELECT
    test_name,
    DATE_TRUNC('week', collected_at) as week,
    COUNT(*) as executions,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures,
    100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*) as flake_rate
FROM test_cases
WHERE test_name IN (
    -- Tests that have both passes and failures
    SELECT test_name FROM test_cases
    GROUP BY test_name
    HAVING SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) > 0
       AND SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
)
GROUP BY test_name, DATE_TRUNC('week', collected_at)
ORDER BY test_name, week;
```

## Related

- [Failure Classification](../failures/classification.md)
- [Per-Test Breakdown](../failures/per-test.md)
- [Test Framework](../../prow/test-framework.md)
