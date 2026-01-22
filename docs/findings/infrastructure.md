# Infrastructure Issues

## Overview

Infrastructure failures represent problems with the underlying test execution environment rather than code defects. These include timeouts, image pull failures, network issues, and resource contention.

This analysis examines build logs to identify infrastructure-related failure patterns and their impact on CI reliability.

## Overall Statistics

```sql
-- Infrastructure failure breakdown
WITH infra_patterns AS (
    SELECT
        tr.build_id,
        tr.pr_number,
        tr.result,
        CASE WHEN bl.log_content LIKE '%timeout%' OR bl.log_content LIKE '%timed out%' OR bl.log_content LIKE '%deadline exceeded%' THEN 1 ELSE 0 END as has_timeout,
        CASE WHEN bl.log_content LIKE '%ImagePull%' OR bl.log_content LIKE '%pull image%' OR bl.log_content LIKE '%ErrImagePull%' THEN 1 ELSE 0 END as has_image_pull,
        CASE WHEN bl.log_content LIKE '%connection refused%' OR bl.log_content LIKE '%dial tcp%' OR bl.log_content LIKE '%network%unreachable%' THEN 1 ELSE 0 END as has_network,
        CASE WHEN bl.log_content LIKE '%pod%not%ready%' OR bl.log_content LIKE '%waiting for pods%' OR bl.log_content LIKE '%ContainerCreating%' THEN 1 ELSE 0 END as has_pod_startup
    FROM build_logs bl
    JOIN test_runs tr ON bl.run_id = tr.id
    WHERE tr.result = 'FAILURE'
        AND bl.log_content IS NOT NULL
)
SELECT
    'Timeout' as issue_type,
    SUM(has_timeout) as affected_builds,
    COUNT(DISTINCT CASE WHEN has_timeout = 1 THEN pr_number END) as affected_prs,
    ROUND(100.0 * SUM(has_timeout) / COUNT(*), 1) as pct_of_failures
FROM infra_patterns
[... UNION ALL for other categories ...]
```

**Results** (of 4,193 failed builds analyzed):

| Infrastructure Issue | Affected Builds | Affected PRs | % of Failures |
|---------------------|-----------------|--------------|---------------|
| **Timeout** | **2,915** | 499 | **69.5%** |
| **Pod Startup Issues** | **2,150** | 413 | **51.3%** |
| **Image Pull Failures** | 737 | 163 | **17.6%** |
| **Network Issues** | 469 | 172 | **11.2%** |

**Critical Finding**: **69.5% of all failed builds (2,915 builds)** show timeout-related errors in logs. More than half (51.3%) have pod startup issues. Many builds have multiple infrastructure problems.

**Note**: These categories overlap - a single build can have multiple infrastructure issues (e.g., pod startup timeout, then image pull failure).

### Total Infrastructure Failures

- **Total failed builds analyzed**: 4,193
- **Builds with timeout issues**: 2,915 (69.5%)
- **Builds with pod startup issues**: 2,150 (51.3%)
- **Builds with image pull issues**: 737 (17.6%)
- **Builds with network issues**: 469 (11.2%)

**Percentage of all failures**: Given that infrastructure issues overlap and affect **69.5%+ of failures**, and considering the [Same-SHA Analysis](same-sha-analysis.md) shows 95% of failures aren't code-related, **infrastructure problems are the primary cause of CI failures**.

## Common Infrastructure Problems

### Timeout Failures

**Statistics**:
- **2,915 builds** (69.5% of failures) contain timeout-related errors
- **499 PRs** affected (57% of all PRs with failures)
- Most common infrastructure problem

**Common Timeout Patterns**:

1. **Context deadline exceeded** - Kubernetes operations timing out
2. **Timed out waiting for...** - Resource readiness timeouts
3. **Operation timeout** - API server or network operation timeouts
4. **Test execution timeout** - E2E tests hitting time limits

**Impact**:
- Failed runs take **3x longer** than successful runs (75.7 min vs 26.5 min avg)
- Timeouts often mean tests run to completion before being killed
- Wastes maximum CI resources - full timeout duration before failure

**Root Causes**:
1. **Resource contention** - Competing workloads slow down operations
2. **Infrastructure degradation** - Cluster performance varies over time
3. **Flaky tests** - Non-deterministic timing dependencies
4. **Insufficient timeout values** - Some operations legitimately need longer

**Evidence from [Time Cost Analysis](time-cost.md)**:
- Tests during peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT) have 21% lower success rates
- Off-peak hours (5-7 AM UTC / 12-2 AM EST / 1-3 AM EDT) show best success rates
- Clear correlation between infrastructure load and timeout failures

### Image Pull Failures

**Statistics**:
- **737 builds** (17.6% of failures) contain image pull errors
- **163 PRs** affected (19% of all PRs with failures)
- Second most common infrastructure issue after timeouts

**Common Error Patterns**:

1. **ErrImagePull** - Image registry not responding or image not found
2. **ImagePullBackOff** - Kubernetes giving up after repeated failures
3. **Registry authentication failures** - Credential issues
4. **Network timeout pulling images** - Registry connectivity problems

**Root Causes**:
1. **Registry availability** - quay.io, gcr.io, docker.io intermittent issues
2. **Rate limiting** - Registry throttling pull requests
3. **Network issues** - Between cluster and registry
4. **Authentication expiry** - Pull secrets timing out

**Impact**:
- Immediate test failure - can't proceed without images
- Often cascades to timeout as retries consume time
- Affects build and test jobs differently:
  - **Build jobs** (bundle, images): Less affected (2-4% failure time)
  - **E2E jobs**: More affected (need to pull test images)

**Weekly Trend**:
Image pull failures show variability week-to-week (17-58 failures per week in sample), suggesting intermittent registry issues rather than systematic problems.

### Pod Startup Issues

**Statistics**:
- **2,150 builds** (51.3% of failures) contain pod startup errors
- **413 PRs** affected (47% of all PRs with failures)
- Often overlaps with timeout failures (pods don't become ready in time)

**Common Patterns**:

1. **Pods not ready** - Containers fail health checks
2. **Waiting for pods** - Test waits indefinitely for pod readiness
3. **ContainerCreating** - Stuck in creation state
4. **CrashLoopBackOff** - Container repeatedly crashes

**Root Causes**:
1. **Resource exhaustion** - Insufficient CPU/memory for pod scheduling
2. **Node issues** - Node not ready or cordoned
3. **Image pull failures** - Can't start without image (overlaps with image pull category)
4. **Application initialization failures** - Container starts but app crashes

**Correlation with Other Issues**:
Pod startup problems often trigger cascading failures:
- Pod won't start → timeout waiting for readiness → test fails
- Image pull fails → pod stuck in ContainerCreating → timeout

### Network Issues

**Statistics**:
- **469 builds** (11.2% of failures) contain network-related errors
- **172 PRs** affected (20% of all PRs with failures)
- Less common but highly disruptive when they occur

**Common Error Patterns**:

1. **Connection refused** - Service not listening or unavailable
2. **Dial tcp: timeout** - Network connectivity issues
3. **Network unreachable** - Routing problems
4. **DNS resolution failures** - Can't resolve service names

**Root Causes**:
1. **Service mesh issues** - Istio/Envoy configuration problems
2. **Network policy** - Overly restrictive policies blocking traffic
3. **DNS issues** - CoreDNS pod problems or configuration
4. **Inter-node networking** - CNI plugin issues

**Test Impact**:
Network issues particularly affect:
- **API server communication** - Can't create/read resources
- **Service-to-service tests** - Testing microservice interactions
- **External resource access** - Webhooks, external APIs

### Resource Exhaustion

**Note**: While not directly measured in log pattern analysis (no OOMKilled instances found), resource exhaustion is implied by:

1. **Pod startup failures** - Can't schedule due to insufficient resources
2. **Timeout during resource operations** - Slow response under load
3. **Time-of-day correlation** - Peak hours show worse performance

**Evidence**:
- **51.3% of failures** involve pod startup issues (often resource-related)
- **Peak hour degradation** - 1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT shows 52-58% success vs 70%+ off-peak
- **Infrastructure contention** - Shared cluster resources compete

**Indicators in Data**:
- Pods pending for extended periods
- Node pressure conditions
- Cluster-wide performance degradation during business hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT)

## Time of Day Correlation

```sql
-- Analyze time of day correlation with infrastructure failures
WITH infra_failures AS (
    SELECT
        EXTRACT(HOUR FROM tr.started_at) as hour_utc,
        COUNT(*) as total_failures,
        SUM(CASE WHEN bl.log_content LIKE '%timeout%' THEN 1 ELSE 0 END) as timeout_failures
    FROM build_logs bl
    JOIN test_runs tr ON bl.run_id = tr.id
    WHERE tr.result = 'FAILURE'
    GROUP BY EXTRACT(HOUR FROM tr.started_at)
)
SELECT hour_utc, total_failures, timeout_failures,
       ROUND(100.0 * timeout_failures / total_failures, 1) as timeout_pct
FROM infra_failures ORDER BY hour_utc;
```

**Key Findings**:

| Time Period (UTC) | EST/EDT | Total Failures | Timeout % | Pattern |
|-------------------|---------|----------------|-----------|---------|
| **Off-peak (2-4 AM)** | 9 PM-11 PM EST / 10 PM-12 AM EDT | 67 | **88.2%** | Very high timeout rate, low volume |
| **Morning (6-8 AM)** | 1-3 AM EST / 2-4 AM EDT | 329 | **75.0%** | Moderate timeout rate |
| **Peak (1-4 PM)** | 8-11 AM EST / 9 AM-12 PM EDT | 1,429 | **64.2%** | High volume, lower timeout % |
| **Evening (7-11 PM)** | 2-6 PM EST / 3-7 PM EDT | 620 | **73.2%** | Moderate volume and rate |

**Interpretation**:

1. **Off-peak high timeout rates** - Fewer runs, but those that run have high failure rates (possibly maintenance windows or degraded clusters)
2. **Peak hour volume** - Most tests run 9 AM - 6 PM UTC / 4 AM - 1 PM EST / 5 AM - 2 PM EDT (business hours)
3. **Peak hour timeout rate** - Lower percentage but massive absolute volume (1,429 failures)
4. **Consistent pattern** - 64-88% of failures involve timeouts regardless of time

**Correlation with Success Rates** (from [Time Cost Analysis](time-cost.md)):
- Best success: 5-7 AM UTC / 12-2 AM EST / 1-3 AM EDT (70.8%)
- Worst success: 3 PM UTC / 10 AM EST / 11 AM EDT (52.6%), 9 PM UTC / 4 PM EST / 5 PM EDT (49.7%)
- Infrastructure contention during peak hours drives failures

## Trends Over Time

```sql
-- Weekly infrastructure failure trends
WITH infra_failures AS (
    SELECT
        DATE_TRUNC('week', tr.started_at)::date as week_start,
        COUNT(*) as total_failures,
        SUM(CASE WHEN bl.log_content LIKE '%timeout%' THEN 1 ELSE 0 END) as timeout_failures,
        SUM(CASE WHEN bl.log_content LIKE '%ImagePull%' THEN 1 ELSE 0 END) as image_pull_failures
    FROM build_logs bl
    JOIN test_runs tr ON bl.run_id = tr.id
    WHERE tr.result = 'FAILURE'
    GROUP BY DATE_TRUNC('week', tr.started_at)
)
SELECT week_start, total_failures, timeout_failures, image_pull_failures,
       ROUND(100.0 * timeout_failures / total_failures, 1) as timeout_pct
FROM infra_failures ORDER BY week_start;
```

**Sample Results** (first 10 weeks):

| Week Starting | Total Failures | Timeout Failures | Image Pull Failures | Timeout % |
|---------------|----------------|------------------|---------------------|-----------|
| 2025-07-14 | 182 | 111 | 58 | 61.0% |
| 2025-07-21 | 147 | 83 | 17 | 56.5% |
| 2025-07-28 | 90 | 73 | 12 | 81.1% |
| 2025-08-04 | 211 | 161 | 32 | 76.3% |
| 2025-08-11 | 105 | 72 | 25 | 68.6% |
| 2025-08-18 | 114 | 70 | 45 | 61.4% |
| 2025-08-25 | 90 | 78 | 2 | 86.7% |
| 2025-09-01 | 141 | 109 | 26 | 77.3% |
| 2025-09-08 | 231 | 198 | 25 | 85.7% |
| 2025-09-15 | 327 | 250 | 42 | 76.5% |

**Observations**:

1. **Timeout rate variability**: 56.5% - 86.7% across weeks
2. **No clear improvement trend**: Timeout issues persist throughout 6-month period
3. **Image pull spikes**: Some weeks show unusually high image pull failures (58 in week 1, 45 in week of Aug 18)
4. **Volume fluctuations**: Total failures vary 90-327 per week

**Conclusion**: Infrastructure issues are persistent and systemic, not improving over time. This suggests underlying platform problems rather than temporary issues.

## Impact

### Time Cost

From [Time Cost Analysis](time-cost.md):

- **Total wasted CI time**: 6,689 hours (278.7 days) on failed/aborted runs
- **Failed runs duration**: 75.7 min average (3x longer than successes)
- **Timeout contribution**: Since 69.5% of failures involve timeouts, approximately **4,670 hours wasted on timeout-related failures**

### Developer Productivity

From [Time Cost Analysis](time-cost.md):

- **75.4% of PRs** require retry commands due to failures
- **Average 4.8 retries per PR** - mostly infrastructure-caused
- **~3,005 `/retest` commands** issued (manual intervention overhead)

### CI Queue Contention

- Failed runs occupy CI resources for full timeout duration
- **2,915 timeout builds** x **75.7 min average** = **3,679 hours** of wasted queue time
- Blocks other PRs from running
- Increases wait time for all developers

### False Negatives

From [Same-SHA Analysis](same-sha-analysis.md):

- **95% of failures** are infrastructure/flakes, not code issues
- **63.1% of PRs** experience same-SHA flakes (identical code passes and fails)
- **46.2% of flakes** succeeded first, then failed (proves infrastructure degradation)

**Conclusion**: Infrastructure failures create a "cry wolf" situation where developers can't trust test results.

## Recommendations

### Immediate Actions

1. **Increase timeout values for known-slow operations**
    - E2E tests currently hit timeout limits (75.7 min avg for failures)
    - Distinguish between "slow but eventually successful" vs "truly stuck"
    - Consider 90-120 minute timeouts for e2e jobs

2. **Add automatic retry logic**
    - Infrastructure failures are transient
    - Auto-retry on timeout (1-2 attempts) before asking developer to intervene
    - Saves 75% of PRs from manual `/retest` commands

3. **Make infrastructure status visible**
    - Show "This failure may be infrastructure-related" on timeout failures
    - Display current cluster health metrics
    - Help developers distinguish real failures from infrastructure issues

### Short-term Improvements

1. **Off-peak scheduling**
    - Encourage test runs during 5-7 AM UTC / 12-2 AM EST / 1-3 AM EDT (best success rates: 70%+)
    - Deprioritize non-critical tests during peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT)
    - Reduce infrastructure contention

2. **Dedicated test clusters**
    - Isolate CI workloads from production traffic
    - Reduce resource contention
    - More predictable performance

3. **Image registry optimization**
    - Pre-pull common images to cluster nodes
    - Use image pull-through cache
    - Reduce registry network traffic by 17.6%

4. **Monitoring and alerting**
    - Track infrastructure failure rates in real-time
    - Alert when timeout rate exceeds threshold (>75%)
    - Proactively identify cluster degradation

### Long-term Systemic Fixes

1. **Infrastructure capacity planning**
    - Current peak hours (1-4 PM UTC / 8-11 AM EST / 9 AM-12 PM EDT) show 52-58% success vs 70%+ off-peak
    - Add cluster capacity to handle peak load
    - Scale node pools based on test demand

2. **Fail-fast patterns**
    - Detect infrastructure issues early (first 5 minutes)
    - Abort quickly instead of waiting for timeout
    - Saves ~70 minutes per timeout failure

3. **Root cause analysis**
    - Investigate why 69.5% of failures involve timeouts
    - Are timeout values too aggressive?
    - Are infrastructure provisioning times increasing?

4. **Test reliability improvements**
    - Fix tests with timing dependencies
    - Improve resource cleanup between tests
    - Better isolation to prevent cascading failures

## Related Analysis

- [Same-SHA Analysis](same-sha-analysis.md) - 95% of failures aren't code issues (infrastructure/flakes)
- [Time Cost Analysis](time-cost.md) - 55.3% of CI time wasted, infrastructure contention by time of day
- [Flake Rate Analysis](flake-rate.md) - 99.6% of failures are from flaky tests (often infrastructure-triggered)
- [Infrastructure Failure Types](../analysis/failure-types/01-infrastructure.md) - Detailed classification methodology
