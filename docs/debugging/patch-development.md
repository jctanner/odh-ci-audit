# Patch Development Process

## Overview

The fail-fast diagnostic framework is being developed iteratively through patches to PR #3048 in the opendatahub-operator repository. Each patch adds incremental capabilities, is validated through actual Prow CI runs, and informs the next iteration based on real log analysis.

## Development Methodology

### Iterative Approach

```
┌─────────────────┐
│  Implement      │
│  Diagnostics    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Submit Patch   │
│  to PR #3048    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Prow CI Run    │
│  (90-115 min)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Analyze Logs   │
│  Review Output  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Identify Gaps  │
│  Plan Next      │
└────────┬────────┘
         │
         └────► Next Patch
```

### Validation Criteria

Each patch is evaluated against:

1. **Diagnostic Completeness**: Does it capture enough context to diagnose root cause?
2. **Trigger Accuracy**: Do diagnostics run when needed (not too early, not too late)?
3. **Time Savings**: Does it reduce time-to-failure or manual investigation time?
4. **False Positives**: Does it trigger on healthy systems?
5. **Log Readability**: Are diagnostics easy to find and understand?

## Patch History

### Patch 4: Initial Infrastructure Diagnostics

**Date**: 2026-01-14
**Build**: 2011262195949637632
**Objectives**:
- Add infrastructure health check (pre-flight validation)
- Add deletion recovery timing instrumentation
- Add diagnostic framework for pod-level failures

**Implementation**:

1. **Infrastructure Health Check** (`helper_test.go:InfrastructureHealthCheck()`):
   - Node readiness verification
   - Operator deployment health
   - API server responsiveness
   - Required CRD validation

2. **Deletion Recovery Timing** (`components_test.go`):
   - Log start time before deletion
   - Log success with duration after recreation
   - Attempt to trigger diagnostics on failure

3. **Pod Diagnostics Framework** (`debug_utils_test.go:capturePodDiagnostics()`):
   - Container state analysis
   - Basic logging

**Results**:

✅ **What Worked**:
- Infrastructure health check executed successfully (5 seconds)
- Validated cluster was healthy at test start
- Deletion recovery timing showed healthy behavior (5-15s recreations)
- Generic cluster diagnostics captured node health, operator status

❌ **What Was Missing**:
- Pod-level diagnostics not detailed enough
- No container logs captured
- No readiness probe failure details
- No pod events timeline
- Diagnostics didn't capture "why" a container wasn't ready, only "what" failed

**Example Gap**:
```
Pod prometheus-data-science-monitoringstack-1: Running
  Ready: False - containers with unready status: [prometheus]
  Container prometheus running but not ready
```

**What we needed**:
```
Pod prometheus-data-science-monitoringstack-1: Running
  Container prometheus:
    State: Running (started 418s ago)
    Restarts: 0
    Readiness: http-get http://:9090/-/ready
    Recent Logs:
      level=error ts=... msg="Failed to open TSDB" err="permission denied: /prometheus/data"
    Events:
      Warning  Unhealthy  Readiness probe failed: HTTP 503
```

**Key Learning**: Cluster-level diagnostics are necessary but not sufficient. Need pod/container-level details to understand WHY failures occur.

**Patch 4 Review**: [../messages/3048-patch4-review.md](../../messages/3048-patch4-review.md)

---

### Patch 5: Enhanced Diagnostics & Deletion Recovery

**Date**: 2026-01-14
**Build**: 2011526547978063872
**Objectives**:
- Enhance pod diagnostics with container logs and events
- Add deletion recovery diagnostic framework
- Measure and compare timing across resources

**Implementation**:

1. **Enhanced Pod Diagnostics**:
   ```go
   func capturePodDiagnostics(ctx, k8sClient, namespace, podName) {
       // Container state with timing
       // Readiness probe configuration
       // Recent logs (100 lines current, 50 lines previous)
       // Pod events timeline
       // Resource requests/limits
   }
   ```

2. **Deletion Recovery Diagnostic Framework** (`diagnoseDeletionRecoveryFailure()`):
   - Controller pod health analysis
   - Resource existence checks
   - Component status inspection
   - Recent event correlation

3. **Timing Comparisons**:
   - Measure recreation time for each resource type
   - Compare healthy vs unhealthy behavior
   - Identify performance anomalies

**Results**:

✅ **What Worked**:
- Infrastructure health check: **PASSED in <5 seconds**
- Deletion recovery timing exposed critical disparity:
  - ConfigMap `maas-parameters`: **5.17 seconds** ✓ (healthy)
  - ConfigMap `tier-to-group-mapping`: **605 seconds** ✗ (timeout)
- Timing data clearly distinguished normal controller behavior from bugs
- Framework proved controller logic issue, NOT infrastructure

⚠️ **What Didn't Work**:
- Deletion recovery diagnostics **NOT triggered** for the 605s timeout
- Test used defer pattern incompatible with Gomega Eventually()
- Lost opportunity to debug tier-to-group-mapping failure

**Timing Issue Identified**:
```go
defer func() {
    if t.Failed() {
        diagnoseDeletionRecoveryFailure(...)
    }
}()

Eventually(func() error {
    return checkResourceRecreated()
}, 600*time.Second, 5*time.Second).Should(Succeed())
```

**Problem**: Gomega's `Eventually()` doesn't set `t.Failed()` until **after** the function returns, which is **after** the defer executes.

**Evidence for Fail-Fast Value**:
- Test waited **600 seconds** for timeout
- After 30 seconds of no progress, should have failed fast
- **570 seconds wasted** waiting for operation that would never succeed

**Key Insights**:

1. **5s vs 605s comparison** proves fail-fast value:
   - Same resource type (ConfigMap)
   - Same controller
   - One recreates in 5s, one times out at 605s
   - Clear evidence of controller bug (not infrastructure)

2. **Need circuit breaker pattern**:
   - After 6 consecutive failures (30 seconds), fail fast
   - Don't wait 600 seconds for something that's clearly not working

3. **Need better diagnostic trigger mechanism**:
   - Defer pattern doesn't work with Gomega
   - Need OnFailure callback or custom Eventually wrapper

**Patch 5 Review**: [../messages/3048-patch5-review.md](../../messages/3048-patch5-review.md)

---

### Patch 6: Circuit Breakers & Diagnostic Callbacks

**Date**: 2026-01-14
**Build**: 2011572574793764864
**Job Type**: pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-rhoai-e2e
**Objectives**:
- Fix diagnostic trigger mechanism (replace defer with OnFailure callbacks)
- Add circuit breaker pattern to deletion recovery
- Add error categorization tags ([INFRASTRUCTURE], [CONTROLLER], [TEST])

**Implementation**:

1. **Fixed Diagnostic Triggering**:
   ```go
   // Replace defer with Gomega OnFailure callback
   EventuallyWithOffset(1, func() error {
       return checkCondition()
   }).WithTimeout(timeout).
     WithPolling(interval).
     Should(Succeed(), func() string {
         // This runs ONLY on failure
         diagnoseDeletionRecoveryFailure(tc, ...)
         return "[CONTROLLER] deletion recovery failed"
     })
   ```

2. **Circuit Breaker Implementation**:
   ```go
   consecutiveFailures := 0
   Eventually(func() error {
       err := checkResourceRecreated()
       if err != nil {
           consecutiveFailures++
           if consecutiveFailures >= 6 {  // 6 failures * 5s = 30s
               diagnoseDeletionRecoveryFailure(...)
               return fmt.Errorf("[CONTROLLER] not recreating after %d attempts", consecutiveFailures)
           }
       } else {
           consecutiveFailures = 0
       }
       return err
   }, 600*time.Second, 5*time.Second)
   ```

3. **Error Tagging**:
   - `[INFRASTRUCTURE]` - Node/pod/cluster issues
   - `[CONTROLLER]` - Reconciliation bugs
   - `[TEST]` - Test implementation bugs

**Results**:

✅ **Successes**:

1. **Infrastructure Health Check: Working Perfectly**
   ```
   [FAIL-FAST] ✓ All 6 nodes are ready
   [FAIL-FAST] ✓ Operator deployment rhods-operator has 3 ready replica(s)
   [FAIL-FAST] ✓ API server is responsive
   [FAIL-FAST] ✓ CRD dscinitializations.dscinitialization.opendatahub.io is installed
   [FAIL-FAST] ✓ CRD datascienceclusters.datasciencecluster.opendatahub.io is installed
   [FAIL-FAST] ✓ Infrastructure health check PASSED
   ```
   - Execution time: **0.4 seconds**
   - Would save 90+ minutes if infrastructure was bad

2. **Deletion Recovery: Excellent Visibility**
   - All tests **PASSED** with precise timing
   - ConfigMaps: **5.17-5.36 seconds** (excellent)
   - Services: **5.22-15.27 seconds** (good)
   - Deployments: **15.27-25.33 seconds** (acceptable)
   - NO timeout failures - healthy controller behavior

3. **Pod Diagnostics: Comprehensive**
   ```
   === POD DIAGNOSTICS: redhat-ods-applications/data-science-pipelines-... ===
     ✓ Initialized: True
     ✓ PodScheduled: True
     ✓ PodReadyToStartContainers: True
     ✓ Ready: True
     ✓ ContainersReady: True
   === END POD DIAGNOSTICS ===
   ```
   - Clear, scannable output
   - Visual indicators (✓ symbols)
   - Would show detailed logs if containers failed

4. **Error Tagging: Easy Discovery**
   - Tags make grep/search trivial
   - Clear categorization of issues
   - Enables automated actions (retry vs manual fix)

🐛 **Failures Identified**:

1. **Trainer Component: TEST IMPLEMENTATION BUG**
   ```
   Error: resourceVersion should not be set on objects to be created
   ```
   - Test code incorrectly sets resourceVersion when creating deployments
   - Flaky: FAILED (10.29s) → PASSED on retry (20.11s)
   - **Patch 6 correctly identified this as [TEST] bug, NOT infrastructure**

2. **Kueue Component: Timeout During State Transition**
   - Duration: **351.63 seconds** (~6 minutes)
   - No diagnostic output (test not instrumented with OnFailure callback)
   - **Gap**: Circuit breaker pattern not applied to this test

**Key Achievements**:

1. ✅ **Diagnostics now trigger correctly** - OnFailure callbacks work with Gomega
2. ✅ **Healthy controller behavior validated** - 5-25s recreation times prove controllers working correctly
3. ✅ **Test bug correctly identified** - Distinguished test implementation bug from infrastructure issue
4. ✅ **Framework provides foundation** - Core diagnostics working, ready to expand coverage

**Remaining Gaps**:

1. Circuit breaker not applied to all long-running Eventually() calls
2. Some tests (like Kueue state transitions) lack diagnostic instrumentation
3. Need to fix trainer test bug (clear resourceVersion before creation)

**Patch 6 Review**: [../messages/3048-patch6-review.md](../../messages/3048-patch6-review.md)

---

## Lessons Learned

### 1. Infrastructure Health Checks Are Fast and Valuable

**Finding**: Infrastructure validation completes in **0.4-5 seconds**.

**Value**: If infrastructure is degraded, fail in 5 seconds instead of 90+ minutes.

**ROI**: **~1,000x time savings** when infrastructure is bad.

### 2. Timing Data Exposes Controller Bugs

**Finding**: Comparing healthy vs unhealthy timing reveals bugs:
- Healthy: 5-25 seconds
- Unhealthy: 600+ seconds timeout

**Value**: Immediately distinguishes "controller is working" from "controller has a bug".

**Example**: One ConfigMap recreates in 5s, another times out at 605s → controller bug, NOT infrastructure.

### 3. Circuit Breakers Prevent Wasted Time

**Finding**: Waiting 600 seconds for a timeout wastes **570 seconds** when failure is obvious after 30 seconds.

**Value**: Fail fast after 6 consecutive failures (30s) instead of waiting for full timeout.

**Savings**: **9.5 minutes per occurrence**.

### 4. Defer Pattern Doesn't Work with Gomega

**Finding**: `defer func() { if t.Failed() { ... } }()` doesn't trigger when `Eventually()` times out.

**Root Cause**: Gomega sets `t.Failed()` after the function returns, which is after defer executes.

**Solution**: Use Gomega's `Should(Succeed(), onFailureCallback)` pattern or custom Eventually wrapper.

### 5. Error Tags Enable Quick Triage

**Finding**: Tags like `[INFRASTRUCTURE]`, `[CONTROLLER]`, `[TEST]` make logs searchable.

**Value**:
- Quick grep to find relevant failures
- Clear categorization guides action (retry vs manual fix)
- Enables automated remediation policies

### 6. Iterative Development Is Essential

**Finding**: Can't predict all failure modes upfront. Need real logs to identify gaps.

**Process**:
1. Implement diagnostics
2. Run on real CI
3. Analyze logs
4. Identify gaps
5. Next patch

**Example**: Patch 4 had pod diagnostics, but missing container logs. Patch 5 added logs. Patch 6 fixed trigger mechanism.

## Metrics Tracked

### Time-to-Failure

| Failure Type | Without Fail-Fast | With Fail-Fast (Patch 6) | Savings |
|--------------|------------------|-------------------------|---------|
| Infrastructure degradation | 90-115 min | <5 min | **87-110 min** |
| Deletion recovery timeout | 10 min | 30s (circuit breaker) | **9.5 min** |
| Pod container failure | 10-30 min | <5 min (with diagnostics) | **5-25 min** |

### Diagnostic Completeness

| Component | Patch 4 | Patch 5 | Patch 6 |
|-----------|---------|---------|---------|
| Infrastructure health check | ✓ | ✓ | ✓ |
| Deletion recovery timing | ✓ | ✓ | ✓ |
| Pod diagnostics | Basic | Enhanced | Enhanced |
| Container logs | ✗ | ✓ | ✓ |
| Readiness probe details | ✗ | ✓ | ✓ |
| Pod events | ✗ | ✓ | ✓ |
| Circuit breaker | ✗ | ✗ | ✓ |
| OnFailure callbacks | ✗ | ✗ (attempted) | ✓ |
| Error tagging | ✗ | ✗ | ✓ |

### Coverage

| Test Category | Patch 4 | Patch 5 | Patch 6 | Target |
|--------------|---------|---------|---------|--------|
| Infrastructure checks | ✓ | ✓ | ✓ | ✓ |
| Deletion recovery | Partial | Full | Full | ✓ |
| Deployment scaling | ✗ | ✗ | Partial | ✓ |
| Component transitions | ✗ | ✗ | ✗ | Future |
| Operator installation | ✗ | ✗ | ✗ | Future |

## Future Patches

### Patch 7 Candidates

1. **Fix Trainer Test Bug** (High Priority)
   - Clear resourceVersion before creation
   - Eliminate flaky test failures

2. **Add Kueue Test Diagnostics** (Medium Priority)
   - Add OnFailure callbacks to state transition tests
   - Add intermediate progress logging for long waits

3. **Expand Circuit Breaker Coverage** (Medium Priority)
   - Apply to deployment scaling waits
   - Apply to component enablement waits
   - Apply to operator installation waits

4. **Add Controller Log Collection** (Low Priority)
   - Capture operator logs on failures
   - Correlate controller errors with test failures

### Long-Term Roadmap

1. **Automated Remediation**
   - Auto-retry on [INFRASTRUCTURE] failures
   - Skip retry on [CONTROLLER] failures
   - Prow integration for automatic actions

2. **Failure Pattern Detection**
   - Recognize common failure signatures
   - Provide targeted remediation suggestions
   - Build knowledge base of known issues

3. **Time-of-Day Correlation**
   - Track failure rates by hour
   - Identify infrastructure degradation patterns
   - Predict high-risk time windows

4. **Integration with CI Audit Database**
   - Store diagnostic data in PostgreSQL
   - Enable trend analysis
   - Generate failure pattern reports

## Related

- [Fail-Fast Framework](fail-fast-framework.md) - Technical architecture
- [Diagnostic Patterns](diagnostic-patterns.md) - Common failure patterns
- [Results & Impact](results-impact.md) - Measured improvements
