# CI Pipeline Issues

## Overview

Analysis of CI/CD pipeline issues affecting test reliability.

## Job Configuration Problems

### Job Timeout Settings

**Current timeout behavior analysis**:

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

**Key Observations**:

1. **E2E tests hit timeout limits**: Failed e2e runs average 92-95 minutes, with P90 at 134-145 minutes and max at 199-300 minutes. This suggests tests are running until they hit timeout thresholds rather than failing fast.

2. **Success takes longer than failure for e2e**: E2E success runs (115.6 min) take longer than failures (92.0 min), which is unusual. This indicates failures are timeout-based rather than fast-fail errors.

3. **Build jobs are efficient**: Bundle, images, and image-mirror jobs complete in 5-17 minutes on average, showing proper fail-fast behavior.

4. **Timeout threshold appears to be ~120-150 minutes**: P90 durations cluster around 134-145 minutes for e2e jobs, suggesting this is the configured timeout.

**Problems**:
- **No fail-fast detection**: E2E tests run for 90+ minutes even when infrastructure is degraded
- **Timeout too aggressive for legitimate tests**: Some successful e2e runs need 135+ minutes
- **Timeout too generous for failures**: Failed tests waste 92 minutes on average before timing out

### Resource Allocation

From [Infrastructure Issues](infrastructure.md) and [Time Cost Analysis](time-cost.md):

**Current state**:
- **No resource limits visible in data**: Tests compete for shared cluster resources
- **Peak hour degradation**: Success rates drop from 70% (off-peak) to 52-58% (peak hours 1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT)
- **Pod startup failures**: 51.3% of failures involve pod startup issues, suggesting resource exhaustion

**Resource contention evidence**:
- Time-of-day variance: 21% swing in success rates between peak and off-peak
- Infrastructure failures: 87.6% of failures show infrastructure error patterns (timeouts, pod startup, image pulls)
- Cluster degradation: Tests that pass at 5-7 AM UTC fail at 1-4 PM UTC on identical code

**Problems**:
- **Insufficient capacity during peak hours**: 1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT shows 21% lower success rate
- **No resource guarantees**: Tests compete, leading to unpredictable failures
- **No isolation between test runs**: Failed tests can impact concurrent tests on same cluster

### Retry Policies

From [Same-SHA Analysis](same-sha-analysis.md) and [Time Cost Analysis](time-cost.md):

**Current state - Manual retries only**:
- **No automatic retry**: All retries require manual `/retest` commands
- **75.4% of PRs** require manual retry commands (627 out of 832 PRs)
- **Average 4.8 retries per PR** - developers manually retry 4-5 times per PR
- **~3,005 total `/retest` commands** issued in 6-month period

**Impact of no auto-retry**:
- **Developer burden**: Constant monitoring and manual intervention required
- **Wasted developer time**: 529 hours spent waiting on failed tests
- **Increased PR duration**: Median 10.1 hours from first run to first success
- **Queue congestion**: Manual retries add to queue depth

**Evidence auto-retry would help**:
- **95% of failures aren't code issues** ([Same-SHA Analysis](same-sha-analysis.md))
- **63.1% of PRs** experience same-SHA flakes (identical code passes/fails)
- **46.2% of flakes** passed first, then failed later (infrastructure degradation)

**Problems**:
- **No auto-retry on infrastructure failures**: Transient errors require manual intervention
- **No retry budget**: Tests don't distinguish between "retry-worthy" (infrastructure) and "real failure" (code bugs)
- **No smart retry**: Retries happen at same time-of-day, encountering same infrastructure issues

## Infrastructure Capacity

### Peak Usage Times

From [Infrastructure Issues](infrastructure.md) time-of-day analysis:

| Time Period (UTC) | EST/EDT | Success Rate | Pattern |
|-------------------|---------|--------------|---------|
| **Best: 5-7 AM** | 12-2 AM EST / 1-3 AM EDT | **70.8%** | Low infrastructure usage, best reliability |
| **Worst: 3 PM** | 10 AM EST / 11 AM EDT | **52.6%** | Peak business hours, high contention |
| **Worst: 9 PM** | 4 PM EST / 5 PM EDT | **49.7%** | Evening peak, high contention |
| Business hours (9 AM - 6 PM) | 4 AM - 1 PM EST / 5 AM - 2 PM EDT | 52-58% | Most tests run during this window |

**Peak hour impact**:
- **21% variance** in success rate between best (70%) and worst (50%) times
- **1,429 failures** occur during peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT)
- **Infrastructure degradation visible**: Same code passes off-peak, fails during peak

**Analysis**: The CI system clearly has insufficient capacity during US East Coast business hours (9 AM - 12 PM EDT). Tests submitted during this window are **40% more likely to fail** purely due to infrastructure load, not code quality.

### Resource Contention Patterns

From [Infrastructure Issues](infrastructure.md):

**Infrastructure failure breakdown** (69.5% of failures involve these):

| Issue Type | Affected Builds | % of Failures | Root Cause |
|------------|----------------|---------------|------------|
| **Timeouts** | 2,915 | **69.5%** | Operations exceed time limits |
| **Pod Startup Issues** | 2,150 | **51.3%** | Pods can't schedule or start |
| **Image Pull Failures** | 737 | **17.6%** | Registry connectivity/rate limiting |
| **Network Issues** | 469 | **11.2%** | Service mesh, DNS, connectivity |

**Contention patterns**:

1. **Timeout failures dominate**: 69.5% of failures involve timeouts, indicating:
    - Resources not available when needed
    - Operations taking longer under load
    - Cluster performance degrades over time

2. **Pod scheduling failures**: 51.3% involve pod startup issues:
    - Insufficient node capacity
    - Resource exhaustion (CPU/memory)
    - Competing workloads prevent scheduling

3. **Cascading failures**: Issues compound:
    - Can't schedule pod → timeout waiting → test fails
    - Image pull slow → pod startup delayed → timeout → test fails

### Cluster Capacity Issues

**Evidence of insufficient capacity**:

1. **Time-of-day correlation proves capacity problem**:
    - Off-peak (5-7 AM UTC): 70% success rate
    - Peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT): 52-58% success rate
    - **Same tests, same code, different results based purely on time**

2. **No improvement over 6 months**:
    - Weekly failure rates remain flat (56.5%-86.7% timeout rates)
    - No trend toward improvement
    - Systemic capacity issue, not temporary problem

3. **Resource exhaustion indicators**:
    - 51.3% pod startup failures (can't allocate resources)
    - Peak hour degradation (cluster saturated)
    - Infrastructure contention (shared resources compete)

**Current capacity appears to be**:
- **Sufficient for off-peak**: 70%+ success rates at night/early morning
- **Insufficient for peak**: 52-58% success rates during business hours
- **Gap**: Need ~25-30% more capacity to handle peak load at off-peak reliability levels

**Cost of insufficient capacity**:
- **6,689 hours wasted** on failed/aborted runs (278.7 days)
- **4,319 hours wasted** on e2e failures alone (180 days)
- **$670-$2,000+ wasted** in cloud compute costs on failures
- **$52,900 developer productivity loss** from waiting on failed tests

## Artifact Collection Issues

**Good news: Artifact collection is highly reliable**

Analysis of artifact availability across 20,679 test runs:

| Artifact Type | Coverage | Missing | Notes |
|---------------|----------|---------|-------|
| **Build logs** | **100.0%** | 0 runs | Complete coverage across all jobs |
| **Test cases (e2e jobs)** | **99.8%** | 10 runs | Nearly complete junit XML coverage |
| **Test cases (all jobs)** | **99.9%** | 17 runs | Excellent overall coverage |

**Test case coverage by job type**:

| Job Type | Total Runs | With Test Cases | Coverage |
|----------|------------|-----------------|----------|
| e2e-hypershift | 934 | 934 | 100.0% |
| rhoai-e2e | 715 | 715 | 100.0% |
| image-mirror | 4,509 | 4,508 | 100.0% |
| bundle | 4,183 | 4,182 | 100.0% |
| images | 4,158 | 4,153 | 99.9% |
| **e2e** | 5,485 | 5,475 | **99.8%** |

**Findings**:

1. **Excellent artifact collection**: 99.9%+ coverage across all artifact types
2. **No systematic collection failures**: Missing artifacts are rare edge cases (17 out of 20,679 runs)
3. **Reliable junit XML parsing**: Ginkgo/Gomega test output consistently captured
4. **Complete log collection**: 100% of runs have build logs available for analysis

**Minor issues identified** (17 runs missing test cases):
- Likely cause: Job aborted before junit XML could be written
- Impact: Minimal - represents 0.08% of total runs
- Most missing from e2e jobs (10 out of 5,485 = 0.18%)

**Recommendation**: Artifact collection is NOT a problem area. The CI system reliably captures test results and logs. Focus should be on the actual test reliability issues, not artifact collection.

## Recommendations

Based on the analysis above, prioritized by impact and effort:

### Configuration Changes

**Priority 1: Implement Automatic Retry Logic** (High Impact, Low Effort)

- **Auto-retry on infrastructure failures**: 1-2 automatic retries for timeout, image pull, network errors
- **Saves 75.4% of PRs** from manual `/retest` commands
- **Reduces developer burden**: Eliminate ~3,000 manual retries per 6 months
- **Implementation**: Prow supports automatic retries via ProwJob config
- **Expected impact**: Reduce manual retries by 70-80%, improve developer experience dramatically

**Example ProwJob config**:
```yaml
presubmits:
  opendatahub-io/opendatahub-operator:
    - name: pull-ci-opendatahub-operator-e2e
      max_concurrency: 10
      # Add automatic retry on infrastructure failures
      retry_on:
        - timeout
        - pod_startup_failure
        - image_pull_failure
      max_retries: 2  # Allow 2 automatic retries
```

**Priority 2: Implement Fail-Fast Infrastructure Detection** (High Impact, Medium Effort)

- **Early infrastructure health check**: Verify cluster health before starting tests
- **Abort on degraded infrastructure**: Don't run 90-minute test when cluster is already degraded
- **Save ~70 minutes per infrastructure failure**: Current: wait 92 min for timeout. Proposed: fail in <5 min
- **Implementation**: Add pre-test infrastructure health checks (node readiness, resource availability, registry connectivity)
- **Expected impact**: Reduce wasted time from 4,319 hours → ~1,500 hours (save 2,800 hours/year)
- **📖 See**: [Fail-Fast Patterns](../recommendations/fail-fast-patterns.md) for complete implementation guide with code examples

**Priority 3: Adjust Timeout Values** (Medium Impact, Low Effort)

Current problems:
- E2E timeouts appear to be ~120-150 minutes
- Failed tests waste 92 minutes on average
- Some legitimate tests need 135+ minutes

**Proposed timeout strategy**:
```yaml
# Two-tier timeout approach
e2e-jobs:
  infrastructure_timeout: 10 minutes  # Fail fast if infra not ready
  test_timeout: 180 minutes           # Allow legitimate slow tests to complete

bundle-jobs:
  infrastructure_timeout: 2 minutes
  test_timeout: 30 minutes
```

**Benefits**:
- Infrastructure failures detected in 10 min instead of 92 min (82 min savings each)
- Legitimate slow tests can complete (reduce false failures)
- Clear separation between "infra not ready" vs "test too slow"

### Resource Adjustments

**Priority 1: Add Peak-Hour Capacity** (High Impact, High Cost)

**Problem**: 21% lower success rate during peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT)

**Options**:

1. **Add ~25-30% more cluster capacity**:
    - Scale node pools during peak hours (9 AM - 6 PM UTC / 4 AM - 1 PM EST / 5 AM - 2 PM EDT)
    - Cost: ~$15K-25K/month additional cloud spend
    - Benefit: Bring peak-hour success from 52-58% → 70%+ (match off-peak)

2. **Dedicated test clusters** (separate from other workloads):
    - Isolate CI tests from production/dev workloads
    - Guaranteed resource allocation for tests
    - Cost: ~$20K-30K/month
    - Benefit: More predictable performance, eliminate external contention

3. **Hot spare clusters** (see [Hot Spare Analysis](hot-spare-analysis.md)):
    - Pre-provisioned clusters ready for tests
    - Eliminate 10-20 min cluster provisioning delay
    - Cost: $90K-240K/year
    - Benefit: Queue wait reduction, but doesn't fix test flakiness (88% of failures)
    - **Recommendation**: Consider ONLY after fixing test reliability (Tier 1-2 improvements first)

**Priority 2: Off-Peak Test Scheduling** (Medium Impact, Free)

- **Encourage off-peak testing**: 5-7 AM UTC / 12-2 AM EST / 1-3 AM EDT shows 70% success
- **Deprioritize non-urgent tests during peak**: 1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT
- **Implementation**:
    - High-priority (blocking) tests: run immediately
    - Low-priority (optional) tests: queue for off-peak
- **Benefit**: Smooth demand curve, reduce peak contention
- **Cost**: Free, just policy change

**Priority 3: Image Pull-Through Cache** (Medium Impact, Low Cost)

From [Infrastructure Issues](infrastructure.md): 17.6% of failures involve image pull errors

**Implementation**:
- Deploy registry pull-through cache in same datacenter as test clusters
- Pre-pull common images (opendatahub-operator, RHEL base images, test images)
- Reduces external registry network traffic and rate limiting

**Benefit**:
- Reduce image pull failures by 50-70% (from 17.6% → ~5-8%)
- Faster test execution (cached image pulls)
- Less vulnerable to external registry downtime

**Cost**: ~$2K-5K/month for cache infrastructure + storage

### Process Improvements

**Priority 1: Make Infrastructure Status Visible to Developers** (High Impact, Low Effort)

**Problem**: Developers can't distinguish real failures from infrastructure issues

**Implementation**:
- Add infrastructure health badge to PR status checks
- Show "⚠️ Infrastructure degraded - this failure may not be code-related" on infrastructure failures
- Display current success rate by time-of-day in Prow dashboard
- Link to [Same-SHA Analysis](same-sha-analysis.md) data showing 95% of failures aren't code issues

**Benefit**:
- Developers understand when to trust test results
- Reduce frustration from flaky failures
- Better decision-making on when to merge despite failures

**Priority 2: Track and Display Flake Metrics** (Medium Impact, Medium Effort)

**Implementation**:
- Per-test flake rate dashboard (based on data from [Flake Rate Analysis](flake-rate.md))
- Show "⚠️ This test has 81.5% flake rate" on TestOdhOperator failures
- Identify tests with >50% flake rate as "known flaky - informational only"
- Auto-retry known-flaky tests without blocking PR

**Benefit**:
- Transparency on test reliability
- Developers can focus on reliable test failures
- Prioritize fixing worst flaky tests (TestOdhOperator, cluster install)

**Priority 3: Smart Retry Timing** (Low Impact, Medium Effort)

**Problem**: Manual retries happen at same time-of-day, encountering same infrastructure load

**Implementation**:
- If test fails during peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT), delay retry by 4-6 hours
- If test fails during off-peak, retry immediately
- Spread retries across time to avoid concentrating load

**Benefit**:
- Higher success rate on retries (retry during better infrastructure conditions)
- Smoother infrastructure load distribution

## Summary: Top 3 Recommendations

Based on impact vs effort analysis:

1. **Implement auto-retry logic** (1-2 retries on infrastructure failures)
    - Impact: Eliminates 70-80% of manual retries (3,000 → ~600)
    - Effort: Low (Prow config change)
    - Cost: Free
    - **Do this first**

2. **Add fail-fast infrastructure detection** (abort degraded clusters in <5 min)
    - Impact: Save 2,800 hours/year of wasted CI time
    - Effort: Medium (implement health checks)
    - Cost: Minimal
    - **Do this second**

3. **Add peak-hour capacity** (25-30% more during business hours)
    - Impact: Improve peak success from 52-58% → 70%
    - Effort: High (infrastructure provisioning)
    - Cost: $15K-25K/month
    - **Do this third, after measuring impact of #1 and #2**

## Related

- [Infrastructure Issues](infrastructure.md)
- [Prow Architecture](../prow/architecture.md)
