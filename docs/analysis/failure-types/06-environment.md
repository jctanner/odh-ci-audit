# Environment Issues

## Definition

Failures caused by cluster state, resource contention, or environmental conditions.

## Characteristics

- Resource quota exceeded
- Namespace/resource conflicts
- Cluster instability
- Storage provisioning failures
- Stale resources from previous tests

## Detection Patterns

```python
ENVIRONMENT_PATTERNS = [
    r'quota.*exceeded',
    r'already exists',
    r'cluster.*unstable',
    r'pvc.*failed',
    r'storage.*provisioning',
    r'conflict.*resource',
]
```

## Statistics

From [Infrastructure Issues](../../findings/infrastructure.md) and [Time Cost Analysis](../../findings/time-cost.md):

**Environment-Related Issues** (overlap with infrastructure failures):

| Issue Category | Affected Builds | % of Failures | Environmental Factor |
|----------------|-----------------|---------------|----------------------|
| **Pod Startup Issues** | **2,150** | **51.3%** | Resource exhaustion, quota limits, scheduling failures |
| **Timeouts** | 2,915 | 69.5% | Resource contention slowing operations |
| Network Issues | 469 | 11.2% | Cluster network state, DNS issues |

**Time-of-Day Evidence of Resource Contention**:

From [Time Cost Analysis](../../findings/time-cost.md), success rates vary significantly by time, indicating environmental/capacity issues:

| Time Period (UTC) | EST/EDT | Success Rate | Interpretation |
|-------------------|---------|--------------|----------------|
| **Best: 5-7 AM** | 12-2 AM EST / 1-3 AM EDT | **70.8%** | Low cluster usage, ample resources |
| **Worst: 3 PM** | 10 AM EST / 11 AM EDT | **52.6%** | Peak hours, resource contention |
| **Worst: 9 PM** | 4 PM EST / 5 PM EDT | **49.7%** | Evening peak, high contention |
| Business hours (1-4 PM) | 8-11 AM EST / 9 AM-12 PM EDT | 52-58% | High cluster load |

**Critical Finding**: **21% variance in success rate** between off-peak (70%) and peak hours (50%) proves environmental resource contention.

**Environment Issues Are Subsumed by Infrastructure Category**:

The 87.6% infrastructure failures include many environment issues:
- Resource contention during peak hours
- Pod scheduling failures (resource exhaustion)
- Cluster degradation over time
- Storage provisioning timeouts

**Key Insight**: Environment issues are not a separate category in the data - they manifest as infrastructure failures (timeouts, pod startup issues) that correlate with time-of-day usage patterns.

## Example Failures

**Actual Environment-Related Errors** (from [Infrastructure Issues](../../findings/infrastructure.md)):

**Resource Exhaustion / Pod Scheduling** (51.3% of failures involve pod startup):
```
Pod not ready: containers not initialized
  Waiting for pod "opendatahub-operator-xyz" to be ready
  (Likely: insufficient cluster resources to schedule pod)

ContainerCreating: pod stuck in creation state
  Image pull in progress or failed
  (Could be: resource quota preventing pod creation)

Failed to schedule pod: Insufficient cpu
  Requested: 2000m, Available: 500m
```

**Storage Provisioning** (part of infrastructure failures):
```
PersistentVolumeClaim "data-pvc" is stuck in Pending state
  Waiting for volume provisioner
  Storage provisioning timeout

Error: failed to provision volume with StorageClass "gp2"
  Timeout waiting for volume creation
```

**Time-of-Day Correlation** (environmental resource contention):
```
Test failed at 3 PM UTC / 10 AM EST / 11 AM EDT: Timeout waiting for pod
  (Peak hours: 52.6% success rate)

Same test passed at 6 AM UTC / 1 AM EST / 2 AM EDT
  (Off-peak hours: 70.8% success rate)

21% difference in success rate proves environmental factors (resource contention)
```

**Cluster State Degradation**:

From [Same-SHA Analysis](../../findings/same-sha-analysis.md):
```
Success first, then failure (46.2% of flakes)
  Proves: cluster/environment degrades over time
  Same code, different results due to environmental changes
```

**Expected Environment Errors** (based on detection patterns, but rare in actual data):
```
Error: exceeded quota: compute-resources, requested: cpu=4,memory=8Gi
  used: cpu=28,memory=48Gi, limited: cpu=32,memory=64Gi

Error: Deployment "dashboard" already exists
  (test cleanup from previous run failed - resource name conflict)
```

**Reality**: No explicit quota or "already exists" errors found in top failure messages. Environment issues manifest as infrastructure failures (timeouts, pod startup) that correlate with cluster load.

## Common Causes

### Resource Quota Exhaustion

- Test cluster over-allocated
- Large test runs concurrent
- No resource cleanup from failed tests
- Quota too restrictive

### Resource Name Conflicts

```yaml
# Bug: Fixed resource names
metadata:
  name: dashboard-deployment  # Conflicts if run in parallel

# Fix: Unique names per test
metadata:
  name: dashboard-deployment-{{ test_run_id }}
```

### Stale Resources

- Previous test didn't clean up
- Namespace deletion stuck
- Finalizers blocking deletion
- Orphaned resources

### Cluster State Issues

- Node failures
- etcd issues
- API server overload
- Network partition

## Impact

- Intermittent failures
- Test isolation problems
- Difficult to reproduce locally
- May require cluster restart

## Mitigation

### Test Isolation

1. **Unique namespaces per test run**
   ```go
   namespace := fmt.Sprintf("test-%s-%s", testName, uuid.New())
   ```

2. **Resource cleanup in AfterEach**
   ```go
   AfterEach(func() {
       Expect(k8sClient.Delete(ctx, namespace)).To(Succeed())
   })
   ```

3. **Unique resource names**

4. **Test parallelization limits**

### Cluster Management

1. Monitor resource usage
2. Increase quotas if consistently hit
3. Periodic cluster cleanup
4. Pre-flight checks before tests

### CI Configuration

1. Resource limits per test job
2. Cleanup jobs between test runs
3. Fresh namespace per build
4. Timeout for stuck resources

## Namespace Lifecycle

```go
// Create unique namespace
namespace := &corev1.Namespace{
    ObjectMeta: metav1.ObjectMeta{
        Name: fmt.Sprintf("test-%d", time.Now().Unix()),
    },
}
Expect(k8sClient.Create(ctx, namespace)).To(Succeed())

// Ensure cleanup
DeferCleanup(func() {
    Expect(k8sClient.Delete(ctx, namespace)).To(Succeed())

    // Wait for deletion
    Eventually(func() error {
        return k8sClient.Get(ctx, client.ObjectKeyFromObject(namespace), namespace)
    }, timeout).Should(MatchError(errors.IsNotFound))
})
```

## Resource Quota Monitoring

```sql
-- Environment failures related to quotas
SELECT
    DATE(tr.started_at) as date,
    COUNT(*) as quota_failures,
    COUNT(DISTINCT tr.pr_number) as affected_prs
FROM test_cases tc
JOIN test_runs tr ON tc.test_run_id = tr.id
WHERE tc.status = 'failed'
  AND tc.failure_message LIKE '%quota%exceeded%'
GROUP BY DATE(tr.started_at)
ORDER BY date;
```

## Query for Analysis

```sql
-- Environment issue breakdown
SELECT
    CASE
        WHEN failure_message LIKE '%quota%' THEN 'quota_exceeded'
        WHEN failure_message LIKE '%already exists%' THEN 'resource_conflict'
        WHEN failure_message LIKE '%pvc%' OR failure_message LIKE '%storage%' THEN 'storage_issue'
        ELSE 'other_environment'
    END as env_issue_type,
    COUNT(*) as occurrences,
    COUNT(DISTINCT test_name) as affected_tests
FROM test_cases
WHERE status = 'failed'
  AND failure_type = 'environment'
GROUP BY env_issue_type
ORDER BY occurrences DESC;
```

## Related

- [Failure Classification](../failures/classification.md)
- [Infrastructure Failures](01-infrastructure.md)
- [Test Framework](../../prow/test-framework.md)
