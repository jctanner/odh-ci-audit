# Failure Analysis - Overview

## Purpose

Identify and classify test failures to:

- Understand failure patterns
- Quantify reliability metrics
- Identify root causes
- Prioritize fixes

## Data Sources

```sql
-- Failed test runs
SELECT COUNT(*) FROM test_runs WHERE result = 'FAILURE';

-- Failed test cases
SELECT COUNT(*) FROM test_cases WHERE status = 'failed';

-- Build logs with errors
SELECT COUNT(*) FROM build_logs WHERE error_lines IS NOT NULL;
```

## Failure Metrics

### Test Run Level

- **Failure Rate**: `failed_runs / total_runs`
- **Success Rate**: `successful_runs / total_runs`
- **Abort Rate**: `aborted_runs / total_runs`

### Test Case Level

- **Test Failure Rate**: `failed_cases / total_cases`
- **Test Pass Rate**: `passed_cases / total_cases`
- **Flake Rate**: Tests that fail intermittently

## Failure Classification

**Categories** (from CLAUDE.md):

1. **Infrastructure**: Timeouts, network, pod issues, image pull
2. **Test Flakes**: Race conditions, intermittent failures
3. **Code Regressions**: Assertions, panics, nil pointers
4. **Configuration**: Missing config, YAML errors, permissions
5. **Dependencies**: Missing operators, CRDs, webhooks
6. **Environment**: Cluster state, resource contention

## Classification Methodology

### Pattern Matching

Match failure messages against known patterns:

```python
infrastructure_patterns = [
    r'timeout waiting for pod',
    r'image pull.*failed',
    r'context deadline exceeded',
    r'connection refused',
]

flake_patterns = [
    r'Eventually timed out',
    r'Intermittent failure',
    r'race detected',
]
```

### Manual Classification

For ambiguous failures:

- Examine failure message
- Review stacktrace
- Check build logs
- Consider context (PR changes, timing)

## Key Questions

1. What is the overall failure rate?
2. Which failure types are most common?
3. Are failures trending up or down?
4. Which tests are most flaky?
5. Are there patterns by PR, author, or time?

## Actual Findings

From comprehensive analysis across [Common Failures](../../findings/common-failures.md), [Flake Rate](../../findings/flake-rate.md), and [Infrastructure Issues](../../findings/infrastructure.md):

### Overall Failure Metrics

**Test Run Level** (6-month period, July 2025 - January 2026):

| Result | Runs | % of Total | Avg Duration |
|--------|------|------------|--------------|
| SUCCESS | 12,136 | 58.7% | 26.5 min |
| **FAILURE** | **4,193** | **20.3%** | 75.7 min |
| ABORTED | 4,349 | 21.0% | 19.2 min |
| **Total** | 20,678 | 100% | - |

**Success Rate**: 58.7% (significantly lower than healthy CI systems which typically achieve 85-95%)

**Test Case Level**:

| Status | Test Cases | % of Total |
|--------|------------|------------|
| Passed | 386,299 | 90.8% |
| **Failed** | **39,117** | **9.2%** |
| **Total** | 425,416 | 100% |

**Flake Rate**: **99.6% of failures** are from flaky tests (435 unique tests that both pass and fail)

### Failure Classification - Actual vs Hypothesis

**HYPOTHESIS vs REALITY**:

| Category | Hypothesis | **Actual** | Variance |
|----------|------------|------------|----------|
| Infrastructure | 30-40% | **87.6%** | **+47.6% to +57.6%** ❗ |
| Test Flakes | 20-30% | **99.6%** | **+69.6% to +79.6%** ❗ |
| Code Regressions | 15-25% | **0.1%** | **-14.9% to -24.9%** ❗ |
| Configuration | 10-15% | **12.3%** | Within range ✓ |

**Critical Findings**:

1. **Infrastructure failures dominate**: 87.6% of failures show infrastructure error patterns (timeouts, image pulls, network, pod startup) - **nearly 3x higher than hypothesized**

2. **Test flakes are infrastructure-caused**: The 99.6% flake rate is NOT a test design problem - tests are flaky BECAUSE infrastructure is unreliable

3. **CI is not catching bugs**: Only 0.1% of failures are actual code regressions (4 failures out of 39,117) - **20-250x lower than expected**

4. **Configuration issues**: 12.3% matches hypothesis, but many may actually be infrastructure-triggered (e.g., ConfigMaps not ready due to pod startup delays)

### Root Cause Analysis

From [Common Failures](../../findings/common-failures.md) build log pattern analysis:

| Root Cause | Failures | % | What This Means |
|------------|----------|---|-----------------|
| **Infrastructure** | **3,673** | **87.6%** | Timeouts (69.5%), pod startup (51.3%), image pulls (17.6%), network (11.2%) |
| Configuration | 514 | 12.3% | YAML parsing, permissions, missing config |
| **Code Regression** | **4** | **0.1%** | Panics, nil pointers, assertion failures |
| Unknown/Other | 3 | 0.1% | Unclassified |

### Infrastructure Breakdown

From [Infrastructure Issues](../../findings/infrastructure.md):

| Issue Type | Affected Builds | Affected PRs | % of Failures |
|------------|-----------------|--------------|---------------|
| **Timeouts** | **2,915** | 499 | **69.5%** |
| **Pod Startup Issues** | **2,150** | 413 | **51.3%** |
| Image Pull Failures | 737 | 163 | 17.6% |
| Network Issues | 469 | 172 | 11.2% |

**Note**: Categories overlap - a single build can have multiple infrastructure issues.

### Flake Patterns

From [Flake Rate Analysis](../../findings/flake-rate.md):

- **Total flaky tests**: 435 (tests that both pass and fail)
- **Flaky test failures**: 38,973 (99.6% of all failures)
- **Consistently failing tests**: Only 144 failures (0.4%)

**Same-SHA Evidence** (from [Same-SHA Analysis](../../findings/same-sha-analysis.md)):

- **1,527 PR+SHA combinations** had identical code produce both pass and fail
- **63.1% of PRs** experienced same-SHA flakes
- **75.4% of PRs** required manual `/retest` commands (avg 4.8 retries per PR)
- **Conservative estimate**: 95% of failures are infrastructure/flakes, only 5% potentially code-related

### Top Failing Tests

From [Common Failures](../../findings/common-failures.md):

| Test | Executions | Failures | Failure Rate |
|------|-----------|----------|--------------|
| **TestOdhOperator** | 5,373 | **4,378** | **81.5%** |
| cluster install: overall | 405 | 372 | 91.9% |
| Run multi-stage test test phase | 8,157 | 2,905 | 35.6% |
| Run...opendatahub-operator-e2e... | 3,489 | 2,250 | 64.5% |
| TestOdhOperator/services | 2,803 | 1,753 | 62.5% |

**TestOdhOperator alone accounts for 11.2% of ALL test failures** (4,378 out of 39,117).

## Analysis Approach

1. Calculate overall failure rates
2. Classify failures by type
3. Identify temporal patterns
4. Find most problematic tests
5. Correlate with code changes

## Related

- [Classification Methodology](classification.md)
- [Time Series Analysis](timeseries.md)
- [Per-Test Breakdown](per-test.md)
- [SQL & Python](code.md)
