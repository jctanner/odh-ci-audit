# Timeout Strategy

## Priority: 3

**Impact**: Medium - Reduce false failures, faster feedback
**Effort**: Low - Configuration changes
**Cost**: Free
**Timeline**: 2-3 days

## Problem Statement

### Current Timeout Behavior

**E2E tests run for 90+ minutes before timing out**, even when infrastructure is clearly degraded.

**Data from CI Audit**:

| Job Type | Result | Avg Duration | P90 | Max | Observation |
|----------|--------|--------------|-----|-----|-------------|
| **e2e** | FAILURE | **92.0 min** | 134.2 min | **300.1 min** | Hit timeout limit, waste time |
| **e2e** | SUCCESS | 115.6 min | 133.9 min | 236.4 min | Complete naturally |
| e2e-hypershift | FAILURE | 87.4 min | 138.8 min | 224.6 min | Hit timeout limit |
| rhoai-e2e | FAILURE | 94.8 min | 145.1 min | 199.0 min | Hit timeout limit |

**Key Problems**:

1. **Failed tests are SHORTER than successful** (92 min vs 115 min) - failures hit timeout thresholds
2. **Timeout appears to be ~120-150 minutes** based on P90 clustering
3. **No fail-fast** - tests run full duration even when cluster is degraded from minute 1
4. **Ambiguous errors** - "Test timed out" doesn't distinguish infrastructure vs slow code

### Current vs Desired Behavior

**Current**:
```
00:00 - Test starts, cluster already degraded
00:05 - First operation times out (5 min timeout)
00:15 - Second operation times out (10 min timeout)
00:30 - Third operation times out (15 min timeout)
...
01:32 - Overall job timeout reached
Result: "Test timed out" (infrastructure or code issue?)
```

**Desired**:
```
00:00 - Test starts
00:00 - Infrastructure health check (30 sec)
00:00 - FAIL: "Infrastructure degraded - cluster has no resources"
Result: Clear signal, saves 91.5 minutes
```

## Solution: Two-Tier Timeout Strategy

### Core Concept

Separate timeouts for **infrastructure readiness** vs **test execution**:

1. **Infrastructure Timeout (Short)**: 5-10 minutes to detect cluster issues
2. **Test Timeout (Longer)**: 180+ minutes for legitimate slow tests

Benefits:
- **Fast failure** on infrastructure issues (5-10 min vs 92 min)
- **Fewer false failures** - legitimate slow tests can complete
- **Clear signals** - "infrastructure timeout" vs "test timeout"
- **Saved compute** - 500-800 hours/year

### Expected Impact

| Metric | Current | With Two-Tier Timeouts | Improvement |
|--------|---------|------------------------|-------------|
| Time to detect infrastructure failure | 92 min avg | 5-10 min | 82-87 min saved per failure |
| False timeout failures | ~15% of timeouts | <5% | 66% reduction |
| Wasted CI hours (timeouts) | ~2,000 hours/6mo | ~800 hours/6mo | Save 1,200 hours/6mo |

## Implementation

### Approach 1: Prow Job-Level Timeouts

Configure timeouts at the Prow job level:

**File**: `ci-operator/jobs/opendatahub-io/opendatahub-operator/opendatahub-io-opendatahub-operator-main-presubmits.yaml`

```yaml
presubmits:
  opendatahub-io/opendatahub-operator:
    # E2E Tests
    - name: pull-ci-opendatahub-operator-e2e
      decoration_config:
        timeout: 3h  # Overall job timeout: 180 minutes
        grace_period: 15m  # Cleanup time after timeout

        # Multi-stage timeout configuration
        pod_running_timeout: 10m  # Fail if pod can't start in 10 min (infrastructure)

      spec:
        containers:
        - name: test
          command:
          - ci-operator
          args:
          - --timeout=2h30m  # Actual test timeout: 150 minutes
          # Job timeout (3h) = Test timeout (2.5h) + Grace period (15m) + Buffer (15m)

    # E2E Hypershift
    - name: pull-ci-opendatahub-operator-e2e-hypershift
      decoration_config:
        timeout: 3h
        grace_period: 15m
        pod_running_timeout: 10m

    # RHOAI E2E
    - name: pull-ci-opendatahub-operator-rhoai-e2e
      decoration_config:
        timeout: 3h
        grace_period: 15m
        pod_running_timeout: 10m

    # Build Jobs (much shorter)
    - name: pull-ci-opendatahub-operator-images
      decoration_config:
        timeout: 30m  # Images build quickly
        grace_period: 5m
        pod_running_timeout: 2m

    - name: pull-ci-opendatahub-operator-ci-bundle-validate
      decoration_config:
        timeout: 30m
        grace_period: 5m
        pod_running_timeout: 2m
```

### Approach 2: Test-Level Timeouts (Ginkgo)

Combine with test-level timeouts for fine-grained control:

```go
package e2e_test

import (
    "time"
    . "github.com/onsi/ginkgo/v2"
)

var _ = Describe("TestOdhOperator", func() {
    // Infrastructure checks: short timeout
    Context("Infrastructure health check", NodeTimeout(5*time.Minute), func() {
        It("Should have healthy cluster", func() {
            err := InfrastructureHealthCheck(ctx)
            Expect(err).NotTo(HaveOccurred())
        })
    })

    // Quick operations: medium timeout
    Context("Operator deployment", NodeTimeout(10*time.Minute), func() {
        It("Should deploy operator", func() {
            // ...
        })
    })

    // Slow operations: long timeout
    Context("Full component deployment", NodeTimeout(45*time.Minute), func() {
        It("Should deploy all components", func() {
            // Complex deployment can take 30-40 minutes legitimately
        })
    })
})
```

### Approach 3: Operation-Level Timeouts

Set granular timeouts for individual operations:

```go
const (
    // Infrastructure timeouts (fail fast)
    TimeoutNodeReady          = 2 * time.Minute
    TimeoutPodSchedule        = 5 * time.Minute
    TimeoutImagePull          = 5 * time.Minute

    // Deployment timeouts (allow more time)
    TimeoutPodReady           = 5 * time.Minute
    TimeoutDeploymentRollout  = 10 * time.Minute
    TimeoutOperatorReady      = 3 * time.Minute

    // Component-specific timeouts
    TimeoutDatabaseInit       = 15 * time.Minute  // MariaDB can be slow
    TimeoutKServeReady        = 20 * time.Minute  // Serverless dependencies
    TimeoutDSPReady           = 25 * time.Minute  // Full pipeline stack
)

// Wait for pod with appropriate timeout
func WaitForPodReady(namespace, name string) error {
    return Eventually(func() bool {
        pod, _ := kubeClient.CoreV1().Pods(namespace).Get(ctx, name, metav1.GetOptions{})
        return isPodReady(pod)
    }, TimeoutPodReady, 5*time.Second).Should(Succeed())
}
```

## Timeout Values by Job Type

### E2E Tests

Based on actual duration data (successful tests average 115 min):

```yaml
e2e-jobs:
  # Infrastructure checks
  pod_running_timeout: 10m      # Pod must start in 10 min or infrastructure is broken
  setup_timeout: 15m             # Cluster setup (clone repo, etc.)

  # Test execution
  test_timeout: 150m             # 2.5 hours for actual test execution
                                 # (P90 success = 134 min, so 150 allows headroom)

  # Overall job
  total_timeout: 180m            # 3 hours total (test + setup + cleanup)
  grace_period: 15m              # Cleanup after timeout
```

**Rationale**:
- Successful e2e tests: 115.6 min avg, 133.9 min P90
- Allow 150 min = P90 + 16 min headroom (12% buffer)
- Infrastructure check: 10 min (vs current 92 min to detect failure)

### Build Jobs

Build jobs complete quickly (10-16 min success):

```yaml
build-jobs:
  pod_running_timeout: 2m       # Build pods start fast
  setup_timeout: 5m

  test_timeout: 25m              # Builds: 10-16 min avg, allow 25 for slow ones
  total_timeout: 30m
  grace_period: 5m
```

**Rationale**:
- Build success: 10-16 min avg
- Allow 25 min = more than enough headroom
- Infrastructure check: 2 min (builds fail fast already)

## Integration with Fail-Fast Patterns

Timeouts work best with fail-fast infrastructure checks:

```go
var _ = Describe("TestOdhOperator", func() {
    // TIER 1: Infrastructure check (5 min timeout)
    BeforeEach(NodeTimeout(5*time.Minute), func() {
        By("Running infrastructure health check")
        err := InfrastructureHealthCheck(ctx)
        if err != nil {
            Skip(fmt.Sprintf("[INFRASTRUCTURE] %v", err))
        }
    })

    // TIER 2: Operator setup (10 min timeout)
    Context("Operator deployment", NodeTimeout(10*time.Minute), func() {
        It("Should deploy operator", func() {
            // ...
        })
    })

    // TIER 3: Component tests (per-component timeouts)
    Context("Dashboard", NodeTimeout(15*time.Minute), func() {
        It("Should deploy dashboard", func() {
            // Dashboard is quick, 15 min is generous
        })
    })

    Context("KServe", NodeTimeout(30*time.Minute), func() {
        It("Should deploy KServe", func() {
            // KServe with Serverless is slower
        })
    })
})
```

**Combined effect**:
- Infrastructure degraded → Fail in 5 min (not 92 min)
- Infrastructure healthy, test slow → Allow up to 150 min
- Infrastructure healthy, test fast → Complete in 115 min

## Timeout Error Messages

Improve timeout error messages to distinguish root causes:

### Current (Ambiguous)

```
Error: timeout waiting for condition
FAIL: Test timed out after 120m
```

**Problem**: Developer doesn't know if it's infrastructure or their code.

### Proposed (Clear)

```go
// In test code, add context to timeout errors
func WaitForPodReady(namespace, name string) error {
    err := Eventually(func() bool {
        pod, _ := kubeClient.CoreV1().Pods(namespace).Get(ctx, name, metav1.GetOptions{})

        // Check for infrastructure issues
        if pod.Status.Phase == corev1.PodPending {
            for _, condition := range pod.Status.Conditions {
                if condition.Type == corev1.PodScheduled && condition.Status == corev1.ConditionFalse {
                    // Infrastructure issue - can't schedule pod
                    return false
                }
            }
        }

        return isPodReady(pod)
    }, TimeoutPodReady, 5*time.Second).Should(Succeed())

    if err != nil {
        pod, _ := kubeClient.CoreV1().Pods(namespace).Get(ctx, name, metav1.GetOptions{})

        // Annotate error with context
        if pod.Status.Phase == corev1.PodPending {
            return fmt.Errorf("[INFRASTRUCTURE] Pod %s/%s not ready after %v: stuck in Pending (likely resource exhaustion)",
                namespace, name, TimeoutPodReady)
        }

        return fmt.Errorf("Pod %s/%s not ready after %v: %v",
            namespace, name, TimeoutPodReady, err)
    }

    return nil
}
```

**Result**:
```
[INFRASTRUCTURE] Pod opendatahub/dashboard not ready after 5m: stuck in Pending (likely resource exhaustion)
```

vs

```
Pod opendatahub/dashboard not ready after 5m: CrashLoopBackOff
```

Clear distinction: infrastructure vs code issue.

## Rollout Plan

### Phase 1: Adjust Prow Job Timeouts (Week 1)

1. **Day 1**: Update e2e job timeouts to 3h (from current ~5h?)
2. **Day 2**: Add pod_running_timeout: 10m to all e2e jobs
3. **Day 3**: Monitor for false timeouts (legitimate tests hitting 150 min)
4. **Day 4-5**: Tune based on data

**Success Criteria**:
- ✓ No increase in false timeout failures
- ✓ Infrastructure failures detected faster (avg time to failure < 30 min)

### Phase 2: Add Test-Level Timeouts (Week 2)

1. **Day 1**: Add NodeTimeout to TestOdhOperator infrastructure check (5 min)
2. **Day 2**: Add NodeTimeout to other high-value tests
3. **Day 3-4**: Monitor and tune
4. **Day 5**: Document timeout patterns for developers

**Success Criteria**:
- ✓ Infrastructure failures detected in < 10 min
- ✓ No legitimate tests timing out incorrectly

### Phase 3: Enhanced Error Messages (Week 3)

1. **Day 1-2**: Add infrastructure context to timeout errors
2. **Day 3-4**: Update all WaitFor* functions with better messages
3. **Day 5**: Documentation and examples

**Success Criteria**:
- ✓ Timeout errors clearly indicate infrastructure vs code
- ✓ Developers can act on timeouts without investigation

## Monitoring

Track these metrics to validate timeout strategy:

### Timeout Distribution

```sql
-- Breakdown of timeout failures by duration
SELECT
    CASE
        WHEN duration_minutes < 10 THEN '0-10 min (infrastructure)'
        WHEN duration_minutes < 30 THEN '10-30 min (setup)'
        WHEN duration_minutes < 90 THEN '30-90 min (partial test)'
        WHEN duration_minutes < 150 THEN '90-150 min (near completion)'
        ELSE '150+ min (hit limit)'
    END as timeout_bucket,
    COUNT(*) as occurrences,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
FROM (
    SELECT
        EXTRACT(EPOCH FROM (finished_at - started_at)) / 60 as duration_minutes
    FROM test_runs
    WHERE result = 'FAILURE'
      AND (
          failure_message LIKE '%timeout%'
          OR failure_message LIKE '%timed out%'
          OR failure_message LIKE '%deadline exceeded%'
      )
) timeouts
GROUP BY timeout_bucket
ORDER BY MIN(duration_minutes);
```

**Target**: >70% of timeouts in 0-10 min bucket (infrastructure), <10% in 150+ min (hit limit).

### False Timeout Rate

```sql
-- Tests that timeout, then pass on retry (false timeout)
WITH timeout_retries AS (
    SELECT
        pr_number,
        build_id,
        result,
        LEAD(result) OVER (PARTITION BY pr_number ORDER BY started_at) as next_result
    FROM test_runs
    WHERE failure_message LIKE '%timeout%'
)
SELECT
    COUNT(*) FILTER (WHERE next_result = 'SUCCESS') as false_timeouts,
    COUNT(*) as total_timeouts,
    ROUND(100.0 * COUNT(*) FILTER (WHERE next_result = 'SUCCESS') / COUNT(*), 1) as false_timeout_rate
FROM timeout_retries;
```

**Target**: <10% false timeout rate (tests that timeout but pass on retry with same code).

## Edge Cases

### Legitimate Slow Tests

**Problem**: Some components genuinely take 30-40 minutes to deploy.

**Solution**: Per-component timeout tuning:

```go
var componentTimeouts = map[string]time.Duration{
    "dashboard":           15 * time.Minute,  // Quick
    "modelregistry":       15 * time.Minute,  // Quick
    "kserve":              30 * time.Minute,  // Serverless is slow
    "datasciencepipelines": 40 * time.Minute, // Full stack is slow
}

func WaitForComponent(component string) error {
    timeout := componentTimeouts[component]
    // ... wait with appropriate timeout
}
```

### Cluster Provisioning Delays

**Problem**: Cluster provisioning (for hypershift) can take 15-20 minutes.

**Solution**: Separate provisioning timeout from test timeout:

```yaml
- name: pull-ci-opendatahub-operator-e2e-hypershift
  decoration_config:
    # Cluster provisioning
    cluster_provision_timeout: 25m  # Allow 25 min for cluster to come up

    # After cluster is ready, test timeouts apply
    pod_running_timeout: 10m
    test_timeout: 150m
```

## Related Documentation

- [Fail-Fast Infrastructure Detection](fail-fast-patterns.md) - Complement to timeout strategy
- [Auto-Retry Configuration](auto-retry-configuration.md) - Auto-retry timeout failures
- [CI Pipeline Issues](../findings/ci-pipeline.md) - Data on timeout behavior
- [Duration Analysis](../analysis/duration/per-suite.md) - Actual test durations
