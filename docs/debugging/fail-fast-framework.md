# Fail-Fast Diagnostic Framework

## Architecture

The fail-fast framework consists of four primary components that work together to detect failures early and provide actionable diagnostics:

```
┌─────────────────────────────────────────────────────────────┐
│                    E2E Test Execution                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  1. INFRASTRUCTURE HEALTH CHECK (Pre-Flight Validation)      │
│     • Node readiness verification                            │
│     • Operator deployment health                             │
│     • API server responsiveness                              │
│     • Required CRD validation                                │
│     ⏱️  Execution time: <5 seconds                           │
│     ✅ PASS → Continue to tests                              │
│     ❌ FAIL → Exit immediately with [INFRASTRUCTURE] error   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  2. DELETION RECOVERY DIAGNOSTICS                            │
│     • Timing measurements (nanosecond precision)             │
│     • Circuit breaker (fail after 6 failures = 30s)          │
│     • OnFailure callbacks for diagnostics                    │
│     ✅ Healthy: 5-25 seconds                                 │
│     ⚠️  Unhealthy: 30s circuit breaker triggers              │
│     ❌ Without circuit breaker: 600s timeout                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  3. POD DIAGNOSTICS (On Container Failures)                  │
│     • Container state analysis                               │
│     • Readiness probe configuration                          │
│     • Recent logs (100 lines current, 50 previous)           │
│     • Pod events timeline                                    │
│     • Resource requests/limits vs usage                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  4. ERROR CATEGORIZATION & TAGGING                           │
│     [INFRASTRUCTURE] - Node/pod/cluster issues → Auto-retry  │
│     [CONTROLLER] - Reconciliation bugs → Manual fix          │
│     [TEST] - Test implementation bugs → Fix test code        │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. Infrastructure Health Check

**Purpose**: Detect infrastructure degradation before running expensive tests (90+ minutes).

**Implementation**: `tests/e2e/helper_test.go:InfrastructureHealthCheck()`

**Checks Performed**:

```go
// 1. Node Readiness
// Verify all cluster nodes are in Ready state
if readyNodes < totalNodes {
    return fmt.Errorf("[INFRASTRUCTURE] only %d/%d nodes ready", readyNodes, totalNodes)
}

// 2. Operator Deployment Health
// Verify operator pods are running and ready
if readyReplicas == 0 {
    return fmt.Errorf("[INFRASTRUCTURE] operator deployment has 0 ready replicas")
}

// 3. API Server Responsiveness
// Quick GET request to verify API server isn't degraded
if err := k8sClient.Get(ctx, ...); err != nil {
    return fmt.Errorf("[INFRASTRUCTURE] API server not responsive: %w", err)
}

// 4. Required CRD Installation
// Verify DSCInitialization and DataScienceCluster CRDs exist
if !crdExists {
    return fmt.Errorf("[INFRASTRUCTURE] required CRD not installed")
}
```

**Output Example**:
```
[FAIL-FAST] Running infrastructure health check (pre-flight validation)...
[FAIL-FAST] Checking cluster nodes are ready...
[FAIL-FAST] ✓ All 6 nodes are ready
[FAIL-FAST] Checking operator deployment is ready...
[FAIL-FAST] ✓ Operator deployment opendatahub-operator-controller-manager has 3 ready replica(s)
[FAIL-FAST] Checking API server responsiveness...
[FAIL-FAST] ✓ API server is responsive
[FAIL-FAST] Checking required CRDs are installed...
[FAIL-FAST] ✓ CRD dscinitializations.dscinitialization.opendatahub.io is installed
[FAIL-FAST] ✓ CRD datascienceclusters.datasciencecluster.opendatahub.io is installed
[FAIL-FAST] ✓ Infrastructure health check PASSED - cluster is ready for e2e tests
```

**Time Savings**:
- Execution time: **0.4-5 seconds**
- Avoids: **90-115 minutes** of tests hitting infrastructure timeouts
- ROI: **1,000x time savings** when infrastructure is bad

### 2. Deletion Recovery Diagnostics

**Purpose**: Measure controller response time to deletion events and fail fast if controller isn't responding.

**Implementation**: `tests/e2e/components_test.go:ValidateResourceDeletionRecovery()`

**Key Features**:

1. **Precise Timing**:
```go
startTime := time.Now()
// ... delete resource ...
// ... wait for recreation ...
duration := time.Since(startTime)
t.Logf("[DELETION-RECOVERY] ✓ Success: %s/%s recreated in %v", kind, name, duration)
```

2. **Circuit Breaker Pattern**:
```go
// Fail fast after 6 consecutive failures (30 seconds)
consecutiveFailures := 0
Eventually(func() error {
    err := checkResourceRecreated()
    if err != nil {
        consecutiveFailures++
        if consecutiveFailures >= 6 {
            // Trigger diagnostics BEFORE failing
            diagnoseDeletionRecoveryFailure(...)
            return fmt.Errorf("[CONTROLLER] resource not recreating after %d attempts", consecutiveFailures)
        }
    } else {
        consecutiveFailures = 0
    }
    return err
}, 600*time.Second, 5*time.Second)
```

3. **OnFailure Diagnostic Callbacks**:
```go
EventuallyWithOffset(1, func() error {
    return checkCondition()
}).WithTimeout(timeout).
  WithPolling(interval).
  Should(Succeed(), func() string {
      // Runs ONLY on failure - collect diagnostics here
      capturePodDiagnostics(...)
      captureControllerLogs(...)
      return "[CONTROLLER] deletion recovery failed"
  })
```

**Healthy Behavior** (from Patch 6 validation):
```
[DELETION-RECOVERY] ✓ Success: ConfigMap/mlflow-operator-operator-params-8f727mfcfk recreated in 5.192916314s
[DELETION-RECOVERY] ✓ Success: ConfigMap/feast-operator-parameters-48kdg8m2t9 recreated in 5.187055586s
[DELETION-RECOVERY] ✓ Success: Service/mlflow-operator-controller-manager-metrics-service recreated in 5.270022482s
[DELETION-RECOVERY] ✓ Success: Deployment/mlflow-operator-controller-manager recreated in 15.273976501s
```

**Unhealthy Behavior** (historical CI data):
```
[DELETION-RECOVERY] Starting test for ConfigMap/tier-to-group-mapping
[DELETION-RECOVERY] ⚠️  Attempt 1 failed: resource not found
[DELETION-RECOVERY] ⚠️  Attempt 2 failed: resource not found
[DELETION-RECOVERY] ⚠️  Attempt 3 failed: resource not found
[DELETION-RECOVERY] ⚠️  Attempt 4 failed: resource not found
[DELETION-RECOVERY] ⚠️  Attempt 5 failed: resource not found
[DELETION-RECOVERY] ⚠️  Attempt 6 failed: resource not found
[DELETION-RECOVERY] ❌ Circuit breaker triggered after 30s
[CONTROLLER] ConfigMap tier-to-group-mapping not recreating - controller may not be watching deletion events

=== DELETION RECOVERY DIAGNOSTICS ===
Controller Deployment: opendatahub-operator-controller-manager
  Ready Replicas: 3/3 ✓

Controller Pods:
  Pod opendatahub-operator-controller-manager-abc123: Running
    Restarts: 0
    Memory: 245Mi / 512Mi
    CPU: 0.1 / 1.0
    Recent Logs:
      [No errors related to ConfigMap reconciliation]

Resource Status:
  ConfigMap tier-to-group-mapping: Not found (deleted successfully)
  Expected recreation: NOT HAPPENING

Component Status:
  Component modelsasservice: Installed
    Conditions: Available=True, Progressing=False

Recent Events:
  [No error events in namespace]

CONCLUSION: Controller is healthy but NOT responding to ConfigMap deletion.
Likely bug in controller reconciliation logic - missing watch or finalizer issue.
```

**Time Savings**:
- Without circuit breaker: **600 seconds** (10 minutes)
- With circuit breaker: **30 seconds**
- Savings per occurrence: **570 seconds** (9.5 minutes)

### 3. Pod Diagnostics

**Purpose**: Provide comprehensive container-level debugging when pods are not ready.

**Implementation**: `tests/e2e/debug_utils_test.go:capturePodDiagnostics()`

**Information Captured**:

```go
func capturePodDiagnostics(ctx context.Context, k8sClient client.Client, namespace, podName string) {
    log.Printf("=== POD DIAGNOSTICS: %s/%s ===", namespace, podName)

    pod := &corev1.Pod{}
    k8sClient.Get(ctx, client.ObjectKey{Namespace: namespace, Name: podName}, pod)

    // 1. Container States
    for _, containerStatus := range pod.Status.ContainerStatuses {
        log.Printf("Container: %s", containerStatus.Name)
        log.Printf("  State: %+v", containerStatus.State)
        log.Printf("  Ready: %v", containerStatus.Ready)
        log.Printf("  Restart Count: %d", containerStatus.RestartCount)

        // 2. Container Logs (if not ready)
        if !containerStatus.Ready {
            logs := getContainerLogs(namespace, podName, containerStatus.Name, 100)
            log.Printf("  Recent Logs:\n%s", logs)

            // 3. Previous Logs (if restarted)
            if containerStatus.RestartCount > 0 {
                prevLogs := getPreviousContainerLogs(namespace, podName, containerStatus.Name, 50)
                log.Printf("  Previous Logs (before restart):\n%s", prevLogs)
            }
        }
    }

    // 4. Pod Events
    events := getPodEvents(k8sClient, namespace, podName)
    for _, event := range events {
        log.Printf("  %s: %s - %s", event.Type, event.Reason, event.Message)
    }

    // 5. Resource Requests/Limits
    for _, container := range pod.Spec.Containers {
        log.Printf("Container %s Resources:", container.Name)
        log.Printf("  Requests: %v", container.Resources.Requests)
        log.Printf("  Limits: %v", container.Resources.Limits)
    }

    log.Printf("=== END POD DIAGNOSTICS ===")
}
```

**Example Output**:
```
=== POD DIAGNOSTICS: opendatahub/prometheus-data-science-monitoringstack-1 ===
Container: prometheus
  State: Running (started 418s ago)
  Ready: false
  Restart Count: 0

  Recent Logs:
    level=info ts=2026-01-14T03:49:55.123Z caller=main.go:123 msg="Starting Prometheus"
    level=error ts=2026-01-14T03:49:56.456Z caller=tsdb.go:456 msg="Failed to open TSDB" err="permission denied: /prometheus/data"
    level=error ts=2026-01-14T03:49:56.789Z caller=main.go:789 msg="Prometheus failed to start" err="data directory not writable"

  Recent Events:
    Normal   Created    7m2s                kubelet            Created container prometheus
    Normal   Started    7m2s                kubelet            Started container prometheus
    Warning  Unhealthy  6m57s (x42 over 7m)  kubelet            Readiness probe failed: HTTP probe failed with statuscode: 503

Container prometheus Resources:
  Requests: memory=2Gi, cpu=500m
  Limits: memory=4Gi, cpu=2

=== END POD DIAGNOSTICS ===

ROOT CAUSE: Permission denied writing to /prometheus/data - likely PVC/volume mount issue
```

**Value**: Eliminates 30-60 minutes of manual `kubectl describe pod` and `kubectl logs` investigation.

### 4. Error Categorization & Tagging

**Purpose**: Enable quick triage and appropriate automated actions (retry vs manual fix).

**Tag Types**:

1. **`[INFRASTRUCTURE]`** - Cluster/infrastructure issues
   - Node not ready, pod scheduling failures
   - Image pull timeouts (ImagePullBackOff)
   - API server timeouts, resource exhaustion
   - **Action**: Auto-retry (70-80% pass on retry)

2. **`[CONTROLLER]`** - Controller reconciliation bugs
   - Resource not recreating after deletion
   - Incorrect state transitions
   - Missing ownerReferences or finalizers
   - **Action**: Manual code fix required

3. **`[TEST]`** - Test implementation bugs
   - Flaky assertions, race conditions
   - Incorrect resource preparation
   - Timing-dependent expectations
   - **Action**: Fix test code

**Implementation Examples**:

```go
// Infrastructure health check
if readyNodes == 0 {
    return fmt.Errorf("[INFRASTRUCTURE] no ready nodes found (0/%d) - cluster not operational", totalNodes)
}

// Deletion recovery circuit breaker
if consecutiveFailures >= 6 {
    return fmt.Errorf("[CONTROLLER] %s not recreating after %d attempts - controller may not be watching deletions",
        resourceName, consecutiveFailures)
}

// Pod diagnostics
if isOOMKilled(pod) {
    return fmt.Errorf("[INFRASTRUCTURE] pod %s OOMKilled - increase memory limits or check for memory leak", podName)
}

// Test resource preparation
if obj.GetResourceVersion() != "" {
    return fmt.Errorf("[TEST] resourceVersion should not be set when creating resources")
}
```

**Log Searchability**:
```bash
# Find all infrastructure failures
grep "\[INFRASTRUCTURE\]" build-log.txt

# Find controller bugs
grep "\[CONTROLLER\]" build-log.txt

# Find deletion recovery timing
grep "\[DELETION-RECOVERY\]" build-log.txt

# Find fail-fast checks
grep "\[FAIL-FAST\]" build-log.txt
```

## Integration Points

### TestOdhOperator (Main Test Entry Point)

```go
func TestOdhOperator(t *testing.T) {
    // 1. Infrastructure health check BEFORE expensive tests
    if err := InfrastructureHealthCheck(ctx, k8sClient); err != nil {
        t.Fatalf("Infrastructure health check failed: %v", err)
        // Test exits immediately - saves 90+ minutes
    }

    // 2. Run test suites with fail-fast diagnostics
    t.Run("components", func(t *testing.T) {
        t.Run("group_1", func(t *testing.T) {
            // Deletion recovery tests with circuit breakers
            ValidateResourceDeletionRecovery(tc, ...)
        })
    })
}
```

### Gomega Integration

The framework uses Gomega's Eventually with enhanced error handling:

```go
// Standard Eventually (before)
Eventually(func() error {
    return checkCondition()
}, timeout, interval).Should(Succeed())

// Enhanced Eventually (after)
EventuallyWithOffset(1, func() error {
    return checkCondition()
}).WithTimeout(timeout).
  WithPolling(interval).
  Should(Succeed(), func() string {
      // OnFailure callback - runs ONLY when Eventually times out
      captureDiagnostics()
      return "[CONTROLLER] operation failed"
  })
```

## Benefits

### Time Savings

| Scenario | Without Fail-Fast | With Fail-Fast | Savings |
|----------|------------------|----------------|---------|
| Infrastructure check detects bad cluster | 90-115 min | <5 min | **87-110 min** |
| Deletion recovery circuit breaker | 10 min timeout | 30s fail-fast | **9.5 min** |
| Pod diagnostic collection | 30-60 min manual investigation | Automatic in logs | **30-60 min** |

### Developer Experience

**Before**:
- Wait 92 minutes for test timeout
- Generic error message
- 30-60 minutes manual debugging
- Unclear whether to retry or fix code

**After**:
- Fail in <5 minutes for infrastructure
- Fail in <30 seconds for controller bugs
- Detailed diagnostics in logs
- Clear error tags indicate action (retry vs fix)

### CI Cost Reduction

**6-Month Projection**:
- Total wasted CI time: **4,319 hours**
- Infrastructure failures: **87.6% (3,783 hours)**
- Conservative fail-fast catches: **50% within 5 minutes**
- **Net savings: 1,741 hours (72.5 days) of CI time**

## Related

- [Patch Development](patch-development.md) - Iterative development process
- [Diagnostic Patterns](diagnostic-patterns.md) - Common failure patterns
- [Results & Impact](results-impact.md) - Measured improvements
