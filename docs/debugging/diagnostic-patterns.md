# Diagnostic Patterns

This document catalogs common failure patterns observed in e2e tests and how the fail-fast diagnostic framework identifies and categorizes them.

## Pattern Categories

### Infrastructure Failures (87.6% of all failures)

#### Pattern 1: Node Not Ready

**Symptoms**:
- Pods stuck in Pending state
- Container creation timeouts
- Tests timeout after 90+ minutes

**Root Causes**:
- Kubelet crash or restart
- Node resource exhaustion (memory, disk)
- Network partition

**Diagnostic Output**:
```
[FAIL-FAST] Running infrastructure health check (pre-flight validation)...
[FAIL-FAST] Checking cluster nodes are ready...
[INFRASTRUCTURE] only 5/6 nodes ready
Node worker-2: Not Ready
  Conditions:
    Ready: False - KubeletNotReady: kubelet stopped posting node status
    MemoryPressure: True - NodeHasInsufficientMemory: node has insufficient memory
    DiskPressure: False

[FAIL-FAST] ❌ Infrastructure health check FAILED
```

**Time to Detection**:
- Without fail-fast: **90-115 minutes** (waits for all tests to timeout)
- With fail-fast: **<5 seconds** (infrastructure check)

**Recommended Action**: **Auto-retry** - Infrastructure issue, likely transient.

---

#### Pattern 2: Image Pull Timeout (ImagePullBackOff)

**Symptoms**:
- Pods stuck in ImagePullBackOff or ErrImagePull
- Container never starts
- Tests timeout waiting for deployment

**Root Causes**:
- Registry unavailable or rate-limited
- Network issues reaching registry
- Invalid image name or tag
- Authentication failures

**Diagnostic Output**:
```
=== POD DIAGNOSTICS: redhat-ods-applications/dashboard-abc123 ===
Container: dashboard
  State: Waiting
    Reason: ImagePullBackOff
    Message: Back-off pulling image "quay.io/opendatahub/dashboard:v2.5.0"
  Ready: false
  Restart Count: 0

Recent Events:
  Warning  Failed     2m (x4 over 3m)  kubelet  Failed to pull image "quay.io/opendatahub/dashboard:v2.5.0": rpc error: code = Unknown desc = Error reading manifest v2.5.0 in quay.io/opendatahub/dashboard: unknown: repository opendatahub/dashboard not found
  Warning  Failed     2m (x4 over 3m)  kubelet  Error: ImagePullBackOff
  Normal   BackOff    1m (x6 over 3m)  kubelet  Back-off pulling image

[INFRASTRUCTURE] Pod dashboard-abc123 failing image pull - registry issue or invalid image
```

**Time to Detection**:
- Without fail-fast: **10-30 minutes** (eventually timeout waiting for Ready)
- With fail-fast: **2-5 minutes** (pod diagnostics triggered when container won't start)

**Recommended Action**: **Auto-retry** - Usually transient registry issues. If persists, check image exists.

---

#### Pattern 3: API Server Timeout

**Symptoms**:
- `kubectl` commands hang
- Client-go errors: "context deadline exceeded"
- Tests fail with API server unreachable errors

**Root Causes**:
- API server overload
- Etcd performance issues
- Network latency
- Control plane resource exhaustion

**Diagnostic Output**:
```
[FAIL-FAST] Checking API server responsiveness...
Error performing API server health check: Get "https://api.cluster.example.com:6443/api/v1/namespaces/default": context deadline exceeded (Client.Timeout exceeded while awaiting headers)

[INFRASTRUCTURE] API server not responsive - control plane may be degraded
```

**Time to Detection**:
- Without fail-fast: **90-115 minutes** (all API calls timeout slowly)
- With fail-fast: **<5 seconds** (infrastructure check detects immediately)

**Recommended Action**: **Auto-retry** - Control plane issue, should recover or be replaced.

---

#### Pattern 4: Resource Exhaustion (OOMKilled)

**Symptoms**:
- Pod keeps restarting
- Container exits with code 137
- Memory usage at limit before restart

**Root Causes**:
- Memory leak in application
- Memory limits too low for workload
- Unexpected memory spike

**Diagnostic Output**:
```
=== POD DIAGNOSTICS: opendatahub/modelmesh-controller-abc123 ===
Container: manager
  State: Waiting
    Reason: CrashLoopBackOff
  Last State: Terminated
    Reason: OOMKilled
    Exit Code: 137
    Started: 2026-01-14T12:34:56Z
    Finished: 2026-01-14T12:35:12Z
  Ready: false
  Restart Count: 5

Container manager Resources:
  Requests: memory=256Mi, cpu=100m
  Limits: memory=512Mi, cpu=500m

Previous Logs (before OOMKill):
  level=info msg="Allocating 400MB for cache"
  level=info msg="Loading models from registry"
  fatal error: runtime: out of memory

Recent Events:
  Warning  BackOff  1m (x10 over 5m)  kubelet  Back-off restarting failed container

[INFRASTRUCTURE] Container manager OOMKilled (restart count: 5) - memory limit 512Mi insufficient or memory leak detected
```

**Time to Detection**:
- Without fail-fast: **10-30 minutes** (waits through multiple restart attempts)
- With fail-fast: **2-5 minutes** (pod diagnostics detect crash pattern quickly)

**Recommended Action**: **Manual investigation** - May need memory limit increase or code fix for leak.

---

### Controller Failures (Reconciliation Bugs)

#### Pattern 5: Resource Not Recreating After Deletion

**Symptoms**:
- Delete resource, wait for controller to recreate
- Resource never returns
- Test times out after 10 minutes

**Root Causes**:
- Controller not watching resource deletions
- Missing ownerReference prevents recreation
- Finalizer blocking deletion/recreation
- Controller reconciliation logic bug

**Diagnostic Output**:
```
[DELETION-RECOVERY] Starting test for ConfigMap/tier-to-group-mapping
[DELETION-RECOVERY] ⚠️  Attempt 1 failed: resource not found (5s)
[DELETION-RECOVERY] ⚠️  Attempt 2 failed: resource not found (10s)
[DELETION-RECOVERY] ⚠️  Attempt 3 failed: resource not found (15s)
[DELETION-RECOVERY] ⚠️  Attempt 4 failed: resource not found (20s)
[DELETION-RECOVERY] ⚠️  Attempt 5 failed: resource not found (25s)
[DELETION-RECOVERY] ⚠️  Attempt 6 failed: resource not found (30s)
[DELETION-RECOVERY] ❌ Circuit breaker triggered

=== DELETION RECOVERY DIAGNOSTICS ===
Controller Deployment: opendatahub-operator-controller-manager
  Ready Replicas: 3/3 ✓
  Controller is healthy

Controller Pods:
  Pod opendatahub-operator-controller-manager-abc123: Running
    Restarts: 0
    Memory: 245Mi / 512Mi
    CPU: 0.1 / 1.0
    [No errors in recent logs related to ConfigMap reconciliation]

Resource Status:
  ConfigMap tier-to-group-mapping: Not found (deleted successfully)
  Expected behavior: Controller should recreate within 5-15 seconds
  Actual behavior: NOT RECREATING after 30 seconds

Component Status:
  Component modelsasservice: Installed
    ManagementState: Managed
    Conditions: Available=True, Progressing=False, Degraded=False

Recent Events:
  [No error events in namespace opendatahub]

CONCLUSION:
- Controller deployment is healthy and running
- Controller is NOT responding to ConfigMap deletion event
- This is a controller logic bug, NOT infrastructure issue
- Likely causes:
  1. Controller not watching ConfigMap deletions
  2. Missing ownerReference on ConfigMap
  3. Reconciliation logic doesn't recreate this specific resource

[CONTROLLER] ConfigMap tier-to-group-mapping not recreating after 30s - controller may not be watching deletion events or missing ownerReference
```

**Time to Detection**:
- Without fail-fast: **600 seconds** (10-minute timeout)
- With fail-fast: **30 seconds** (circuit breaker triggers after 6 failures)

**Time Saved**: **570 seconds (9.5 minutes)**

**Recommended Action**: **Manual code fix** - Controller bug, won't pass on retry. Investigate:
1. Check ownerReference on ConfigMap
2. Verify controller watches ConfigMap deletions
3. Review reconciliation logic

---

#### Pattern 6: Component State Stuck

**Symptoms**:
- Component status never transitions to target state
- Stuck in "Progressing" or intermediate state
- Test times out waiting for state change

**Root Causes**:
- Webhook validation blocking state change
- Finalizer preventing state transition
- Controller not handling state change request
- Dependent resources not ready

**Diagnostic Output**:
```
Test: Validate_component_unmanaged_to_removed_transition (Kueue)
Duration: 351.63 seconds (~6 minutes)

Component Status Before State Change:
  Component kueue:
    ManagementState: Unmanaged
    Conditions:
      Available: True
      Progressing: False
      Degraded: False

State Change Requested: Unmanaged → Removed

Component Status After 351s:
  Component kueue:
    ManagementState: Unmanaged (UNCHANGED)
    Conditions:
      Available: True
      Progressing: False (NOT transitioning)
      Degraded: False

Controller Logs:
  [No reconciliation events for kueue component]
  [No errors logged]

CONCLUSION:
- Controller received state change request but did NOT process it
- Component status unchanged after 6 minutes
- No errors indicate controller isn't attempting transition
- Likely webhook validation issue or controller not handling Unmanaged→Removed

[CONTROLLER] Kueue component stuck in Unmanaged state, failed to transition to Removed after 351s
```

**Time to Detection**:
- Without fail-fast: **351 seconds** (current behavior, no circuit breaker applied)
- With fail-fast: **30-60 seconds** (if circuit breaker applied)

**Recommended Action**: **Manual code fix** - Controller or webhook issue. Investigate:
1. Check webhook logs for validation errors
2. Verify controller handles Unmanaged→Removed transition
3. Check for finalizers blocking state change

---

### Test Implementation Bugs

#### Pattern 7: ResourceVersion Set on Create

**Symptoms**:
- Test tries to create resource
- API rejects with "resourceVersion should not be set on objects to be created"
- Flaky: sometimes passes, sometimes fails

**Root Causes**:
- Test code reusing object from GET without clearing metadata
- Trying to create when should be updating (or vice versa)
- Race condition where resource exists vs doesn't exist

**Diagnostic Output**:
```
Test: Validate_update_operand_resources/deployment_kubeflow-trainer-controller-manager
Duration: 10.29s (FAILED) → 20.11s (PASSED on retry)

Error on First Run:
  Error occurred while applying the resource 'redhat-ods-applications/kubeflow-trainer-controller-manager' of kind 'Deployment':
  resourceVersion should not be set on objects to be created

  <*errors.StatusError | 0xc00043b860>:
  Deployment.apps "kubeflow-trainer-controller-manager" is invalid:
  metadata.resourceVersion: Invalid value: "12345": must be specified for an update

Analysis:
- Test is calling CREATE on API server
- Object has resourceVersion field set
- API server rejects CREATE with resourceVersion (only valid for UPDATE)
- Test code bug: should clear resourceVersion before creation
- Flakiness explained:
  1. First attempt: deployment exists → update succeeds
  2. Delete deployment
  3. Second attempt: deployment gone → create fails (resourceVersion set)
  4. Retry: deployment still gone → test properly clears resourceVersion → create succeeds

[TEST] Test code setting resourceVersion on object creation - should clear metadata before CREATE operations

Fix Required:
  // In test helper
  func prepareObjectForCreation(obj *unstructured.Unstructured) {
      obj.SetResourceVersion("")
      obj.SetUID("")
      obj.SetGeneration(0)
  }
```

**Time to Detection**:
- Immediate (test fails quickly with clear error message)
- Diagnostic tagging distinguishes from infrastructure/controller issues

**Recommended Action**: **Fix test code** - Clear resourceVersion before creation.

---

#### Pattern 8: Race Condition in Test Assertions

**Symptoms**:
- Test assertions sometimes pass, sometimes fail
- Timing-dependent: works when system is fast, fails when slow
- No changes to code, but test becomes flaky

**Root Causes**:
- Test doesn't wait for eventual consistency
- Checking condition too early
- Missing Eventually() wrapper

**Diagnostic Output**:
```
Test: Validate_component_enabled
Duration: 0.15s (FAILED) → 5.23s (PASSED on retry)

Error on First Run:
  Expected component status to be "Ready"
  Got: "Progressing"

  Expected:
      <string>: Ready
  to equal:
      <string>: Progressing

Analysis:
- Test checks component status immediately after creation
- Controller needs time to reconcile (5+ seconds)
- First run: check too early, component still Progressing
- Retry: system slower, or test waits longer, component becomes Ready

[TEST] Test assertion executed before controller reconciliation completed - use Eventually() to wait for condition

Fix Required:
  // Instead of:
  status := getComponentStatus()
  Expect(status).To(Equal("Ready"))

  // Use Eventually:
  Eventually(func() string {
      return getComponentStatus()
  }, 30*time.Second, 1*time.Second).Should(Equal("Ready"))
```

**Time to Detection**:
- Immediate (test fails quickly)
- Pattern recognition: fails consistently on first try, passes on retry

**Recommended Action**: **Fix test code** - Wrap assertions in Eventually() to handle eventual consistency.

---

## Diagnostic Decision Tree

```
Test Failure
│
├─ Infrastructure Health Check Failed?
│  ├─ Yes → [INFRASTRUCTURE] → Auto-retry
│  │  ├─ Node not ready → Check kubelet, node resources
│  │  ├─ API server timeout → Check control plane
│  │  ├─ Operator deployment not ready → Check operator logs
│  │  └─ CRD missing → Check installation
│  │
│  └─ No → Infrastructure Healthy → Continue
│
├─ Pod Not Ready?
│  ├─ ImagePullBackOff → [INFRASTRUCTURE] → Auto-retry
│  ├─ OOMKilled → [INFRASTRUCTURE] → Investigate memory limits
│  ├─ CrashLoopBackOff →  Check logs for root cause
│  │  ├─ Permission denied → [INFRASTRUCTURE] → Check PVC, security context
│  │  ├─ Connection refused → [CONTROLLER] → Check service exists
│  │  └─ Application error → [CONTROLLER] → Fix application bug
│  │
│  └─ Container logs show:
│     ├─ "permission denied" → [INFRASTRUCTURE]
│     ├─ "connection refused" → [CONTROLLER] dependency missing
│     ├─ "out of memory" → [INFRASTRUCTURE] OOM
│     └─ Application panic → [CONTROLLER] code bug
│
├─ Resource Not Recreating After Deletion?
│  ├─ Controller pod healthy? → Yes
│  ├─ No errors in controller logs? → Yes
│  ├─ Resource still doesn't recreate after 30s → [CONTROLLER]
│  │  └─ Likely: missing ownerReference, not watching deletions
│  │
│  └─ Controller pod crashing → [CONTROLLER] fix controller crash
│
├─ API Error: "resourceVersion should not be set"?
│  └─ [TEST] → Fix test code to clear resourceVersion before CREATE
│
├─ Flaky: Fails on first try, passes on retry?
│  ├─ Same error both times → [INFRASTRUCTURE] transient issue
│  └─ Different error or timing issue → [TEST] race condition
│
└─ Component State Transition Timeout?
   ├─ Conditions show Progressing=True? → Wait longer or check dependency
   ├─ Conditions show Degraded=True? → Check Degraded message for root cause
   └─ No condition changes for 30+ seconds → [CONTROLLER] not handling transition
```

## Pattern Recognition

### Healthy Timings (Baseline)

| Operation | Expected Time | Threshold for Concern |
|-----------|--------------|---------------------|
| ConfigMap recreation | 5-13s | >30s |
| Service recreation | 5-15s | >30s |
| Deployment recreation | 15-30s | >60s |
| Pod ready after creation | 30-90s | >5min |
| Component state transition | 30-120s | >5min |
| Operator installation | 2-5min | >10min |

### Unhealthy Patterns

| Pattern | Timing | Category | Action |
|---------|--------|----------|--------|
| Node not ready at test start | Immediate | [INFRASTRUCTURE] | Retry |
| API server timeout | <5s | [INFRASTRUCTURE] | Retry |
| Image pull failure | 1-3min | [INFRASTRUCTURE] | Retry |
| OOMKilled container | Variable | [INFRASTRUCTURE] | Investigate |
| ConfigMap never recreates | 600s timeout | [CONTROLLER] | Fix code |
| Component stuck in state | 300-600s | [CONTROLLER] | Fix code |
| ResourceVersion error | Immediate | [TEST] | Fix test |
| Flaky assertion | <1s (inconsistent) | [TEST] | Fix test |

## Related

- [Fail-Fast Framework](fail-fast-framework.md) - Diagnostic architecture
- [Patch Development](patch-development.md) - Iterative development process
- [Results & Impact](results-impact.md) - Measured improvements
