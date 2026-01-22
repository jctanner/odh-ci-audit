# Test Isolation & Cleanup

## Priority: Tier 3

**Impact**: Medium - Reduce cascading failures and resource exhaustion
**Effort**: Medium - Test framework improvements
**Cost**: Free
**Timeline**: 2-3 weeks

## Problem Statement

### Current Behavior: Tests Interfere With Each Other

**Data from CI Audit**:

| Issue | Evidence | Impact |
|-------|----------|--------|
| **Resource exhaustion** | 51.3% of failures involve pod startup issues | Tests compete for limited resources |
| **Cascading failures** | TestOdhOperator hierarchy failures propagate | One failed test causes others to fail |
| **Cleanup failures** | Tests leak resources on failure | Cluster degrades over time within test run |
| **Namespace collisions** | Tests use shared namespaces | Resource conflicts between tests |

**Example cascading failure**:
```
10:00 - Test A starts, creates resources in namespace "test"
10:05 - Test A fails, leaves resources behind
10:10 - Test B starts, tries to use namespace "test"
10:10 - Test B fails: "resource already exists"
10:15 - Test C starts, cluster now has leaked resources
10:15 - Test C fails: "insufficient resources"
```

**Result**: One test failure causes multiple subsequent failures.

## Solution: Proper Test Isolation

### Core Principles

1. **Each test gets its own namespace** - No resource collisions
2. **Cleanup happens ALWAYS** - Even on test failure
3. **Tests are independent** - Can run in any order
4. **Resource limits enforced** - Tests can't starve each other

## Implementation Patterns

### Pattern 1: Unique Namespace Per Test

**Problem**: Tests share namespaces, causing resource conflicts.

**Solution**: Create unique namespace for each test run:

```go
package e2e_test

import (
    "fmt"
    "time"

    . "github.com/onsi/ginkgo/v2"
    . "github.com/onsi/gomega"
    corev1 "k8s.io/api/core/v1"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

var _ = Describe("Component tests", func() {
    var (
        testNamespace string
        ctx           context.Context
    )

    BeforeEach(func() {
        ctx = context.Background()

        // Create unique namespace using timestamp + random suffix
        testNamespace = fmt.Sprintf("test-%s-%d-%s",
            sanitizeTestName(CurrentSpecReport().FullText()),
            time.Now().Unix(),
            randomString(6),
        )

        GinkgoWriter.Printf("Creating test namespace: %s\n", testNamespace)

        ns := &corev1.Namespace{
            ObjectMeta: metav1.ObjectMeta{
                Name: testNamespace,
                Labels: map[string]string{
                    "test-suite": "e2e",
                    "created-by": "ginkgo-test",
                },
            },
        }

        _, err := kubeClient.CoreV1().Namespaces().Create(ctx, ns, metav1.CreateOptions{})
        Expect(err).NotTo(HaveOccurred(), "Failed to create test namespace %s", testNamespace)

        // Wait for namespace to be ready
        Eventually(func() bool {
            ns, err := kubeClient.CoreV1().Namespaces().Get(ctx, testNamespace, metav1.GetOptions{})
            if err != nil {
                return false
            }
            return ns.Status.Phase == corev1.NamespaceActive
        }, 30*time.Second, 2*time.Second).Should(BeTrue())

        GinkgoWriter.Printf("✓ Namespace %s ready\n", testNamespace)
    })

    AfterEach(func() {
        // ALWAYS cleanup, even if test failed
        By(fmt.Sprintf("Cleaning up test namespace: %s", testNamespace))

        // Delete namespace (this cascades to all resources inside)
        err := kubeClient.CoreV1().Namespaces().Delete(
            ctx,
            testNamespace,
            metav1.DeleteOptions{},
        )

        if err != nil {
            GinkgoWriter.Printf("⚠ Warning: Failed to delete namespace %s: %v\n", testNamespace, err)
            // Don't fail the test if cleanup fails, just log
        }

        // Wait for namespace to be fully deleted (important!)
        Eventually(func() bool {
            _, err := kubeClient.CoreV1().Namespaces().Get(ctx, testNamespace, metav1.GetOptions{})
            return errors.IsNotFound(err)
        }, 2*time.Minute, 5*time.Second).Should(BeTrue(),
            "Namespace %s did not delete within timeout", testNamespace)

        GinkgoWriter.Printf("✓ Namespace %s cleaned up\n", testNamespace)
    })

    It("Should deploy dashboard", func() {
        // Test runs in isolated namespace
        dashboard := createDashboard(testNamespace)
        verifyDashboard(testNamespace, dashboard)
        // Namespace auto-cleans after test
    })

    It("Should deploy KServe", func() {
        // Different test, different namespace - no interference
        kserve := createKServe(testNamespace)
        verifyKServe(testNamespace, kserve)
    })
})

func sanitizeTestName(name string) string {
    // Convert test name to valid namespace name
    // Lowercase, replace spaces with hyphens, max 63 chars
    name = strings.ToLower(name)
    name = strings.ReplaceAll(name, " ", "-")
    if len(name) > 30 {
        name = name[:30]
    }
    return name
}

func randomString(length int) string {
    const charset = "abcdefghijklmnopqrstuvwxyz0123456789"
    b := make([]byte, length)
    for i := range b {
        b[i] = charset[rand.Intn(len(charset))]
    }
    return string(b)
}
```

**Benefits**:
- ✅ No namespace collisions between tests
- ✅ Each test starts with clean slate
- ✅ Resources auto-cleanup via namespace deletion
- ✅ Tests can run in parallel safely

### Pattern 2: DeferCleanup for Individual Resources

For resources outside test namespaces (cluster-scoped):

```go
var _ = Describe("Cluster-scoped resources", func() {
    It("Should create ClusterRole", func() {
        clusterRole := &rbacv1.ClusterRole{
            ObjectMeta: metav1.ObjectMeta{
                Name: fmt.Sprintf("test-role-%d", time.Now().Unix()),
            },
            Rules: []rbacv1.PolicyRule{
                // ... rules
            },
        }

        _, err := kubeClient.RbacV1().ClusterRoles().Create(ctx, clusterRole, metav1.CreateOptions{})
        Expect(err).NotTo(HaveOccurred())

        // CRITICAL: Register cleanup IMMEDIATELY after creating resource
        DeferCleanup(func() {
            By(fmt.Sprintf("Cleaning up ClusterRole %s", clusterRole.Name))
            err := kubeClient.RbacV1().ClusterRoles().Delete(
                ctx,
                clusterRole.Name,
                metav1.DeleteOptions{},
            )
            if err != nil && !errors.IsNotFound(err) {
                GinkgoWriter.Printf("⚠ Warning: Failed to delete ClusterRole %s: %v\n",
                    clusterRole.Name, err)
            }
        })

        // Test continues, cleanup happens automatically
        verifyClusterRole(clusterRole.Name)
    })
})
```

**Benefits**:
- ✅ Cleanup happens even if test panics or times out
- ✅ Cleanup runs in reverse order (LIFO)
- ✅ No leaked cluster-scoped resources

### Pattern 3: Resource Quotas Per Namespace

Prevent one test from starving others:

```go
func createNamespaceWithQuota(name string) error {
    // Create namespace
    ns := &corev1.Namespace{
        ObjectMeta: metav1.ObjectMeta{Name: name},
    }
    _, err := kubeClient.CoreV1().Namespaces().Create(ctx, ns, metav1.CreateOptions{})
    if err != nil {
        return err
    }

    // Add resource quota to limit test resource usage
    quota := &corev1.ResourceQuota{
        ObjectMeta: metav1.ObjectMeta{
            Name:      "test-quota",
            Namespace: name,
        },
        Spec: corev1.ResourceQuotaSpec{
            Hard: corev1.ResourceList{
                corev1.ResourcePods:                   resource.MustParse("50"),
                corev1.ResourceCPU:                    resource.MustParse("4"),
                corev1.ResourceMemory:                 resource.MustParse("8Gi"),
                corev1.ResourcePersistentVolumeClaims: resource.MustParse("10"),
            },
        },
    }

    _, err = kubeClient.CoreV1().ResourceQuotas(name).Create(ctx, quota, metav1.CreateOptions{})
    return err
}
```

**Benefits**:
- ✅ One test can't consume all cluster resources
- ✅ Failures are isolated (resource exhaustion in test A doesn't affect test B)
- ✅ Clear error messages when quota exceeded

### Pattern 4: Wait for Complete Cleanup

Ensure namespace is fully deleted before test exits:

```go
func waitForNamespaceDeletion(namespace string, timeout time.Duration) error {
    GinkgoWriter.Printf("Waiting for namespace %s to be fully deleted...\n", namespace)

    // Step 1: Delete namespace
    err := kubeClient.CoreV1().Namespaces().Delete(
        ctx,
        namespace,
        metav1.DeleteOptions{
            PropagationPolicy: &deletePropagationForeground,
        },
    )
    if err != nil && !errors.IsNotFound(err) {
        return fmt.Errorf("failed to delete namespace: %w", err)
    }

    // Step 2: Wait for namespace to be gone
    startTime := time.Now()
    return wait.PollImmediate(5*time.Second, timeout, func() (bool, error) {
        _, err := kubeClient.CoreV1().Namespaces().Get(ctx, namespace, metav1.GetOptions{})

        if errors.IsNotFound(err) {
            elapsed := time.Since(startTime)
            GinkgoWriter.Printf("✓ Namespace %s deleted after %v\n", namespace, elapsed)
            return true, nil
        }

        if err != nil {
            return false, err
        }

        // Still exists, check for stuck resources
        ns, _ := kubeClient.CoreV1().Namespaces().Get(ctx, namespace, metav1.GetOptions{})
        if ns.Status.Phase == corev1.NamespaceTerminating {
            // Log what's blocking deletion
            pods, _ := kubeClient.CoreV1().Pods(namespace).List(ctx, metav1.ListOptions{})
            if len(pods.Items) > 0 {
                GinkgoWriter.Printf("  Waiting for %d pods to terminate...\n", len(pods.Items))
            }
        }

        return false, nil
    })
}
```

**Benefits**:
- ✅ Next test won't see leftover resources
- ✅ Visibility into cleanup progress
- ✅ Detect stuck resources (finalizers, etc.)

### Pattern 5: Parallel Test Execution

With proper isolation, tests can run in parallel:

```go
var _ = Describe("Component tests", Serial, func() {
    // BEFORE: Serial execution (slow)
    // Tests run one at a time: 10 tests × 15 min = 150 min total
})

var _ = Describe("Component tests", func() {
    // AFTER: Parallel execution (fast)
    // Tests run concurrently: 10 tests in parallel = 15 min total

    // Each test gets isolated namespace, no conflicts
    It("Should deploy dashboard", func() { /* ... */ })
    It("Should deploy KServe", func() { /* ... */ })
    It("Should deploy DSP", func() { /* ... */ })
    // All can run at same time safely
})
```

**To enable parallelism**:

```bash
# Run tests with 4 parallel processes
ginkgo -p -procs=4 tests/e2e/

# Or in Prow config
make test-e2e GINKGO_ARGS="-p -procs=4"
```

**Benefits**:
- ✅ Tests complete 4x faster
- ✅ Better resource utilization
- ✅ Catches race conditions

## Advanced Patterns

### Pattern 6: Cleanup on Interrupt/Timeout

Handle test interruption gracefully:

```go
var _ = Describe("Long-running test", func() {
    var testNamespace string

    BeforeEach(func() {
        testNamespace = createTestNamespace()

        // Register cleanup for signals (Ctrl+C, timeout)
        DeferCleanup(func() {
            By("Performing emergency cleanup")
            forceCleanupNamespace(testNamespace)
        })
    })

    It("Should run for a long time", NodeTimeout(30*time.Minute), func() {
        // Long test...

        // If test times out or is interrupted,
        // DeferCleanup still runs
    })
})

func forceCleanupNamespace(namespace string) {
    // Force delete without waiting
    policy := metav1.DeletePropagationBackground
    grace := int64(0)
    err := kubeClient.CoreV1().Namespaces().Delete(
        context.Background(),
        namespace,
        metav1.DeleteOptions{
            PropagationPolicy:  &policy,
            GracePeriodSeconds: &grace,
        },
    )

    if err != nil && !errors.IsNotFound(err) {
        GinkgoWriter.Printf("⚠ Force delete failed for %s: %v\n", namespace, err)
    }
}
```

### Pattern 7: Cleanup Stuck Resources

Handle resources with finalizers that block deletion:

```go
func cleanupNamespaceWithStuckResources(namespace string) error {
    // Try normal delete first
    err := kubeClient.CoreV1().Namespaces().Delete(ctx, namespace, metav1.DeleteOptions{})
    if err != nil && !errors.IsNotFound(err) {
        return err
    }

    // Wait up to 1 minute for normal deletion
    err = wait.PollImmediate(5*time.Second, 1*time.Minute, func() (bool, error) {
        _, err := kubeClient.CoreV1().Namespaces().Get(ctx, namespace, metav1.GetOptions{})
        return errors.IsNotFound(err), nil
    })

    if err == nil {
        return nil // Deleted successfully
    }

    // Still exists - force cleanup stuck resources
    GinkgoWriter.Printf("⚠ Namespace %s stuck, forcing cleanup...\n", namespace)

    // Remove finalizers from all resources
    removeFinalizers(namespace)

    // Wait for deletion to complete
    return wait.PollImmediate(5*time.Second, 1*time.Minute, func() (bool, error) {
        _, err := kubeClient.CoreV1().Namespaces().Get(ctx, namespace, metav1.GetOptions{})
        return errors.IsNotFound(err), nil
    })
}

func removeFinalizers(namespace string) {
    // Get all resources in namespace that might have finalizers
    resources := []struct {
        name     string
        listFunc func() (interface{}, error)
    }{
        {"pods", func() (interface{}, error) {
            return kubeClient.CoreV1().Pods(namespace).List(ctx, metav1.ListOptions{})
        }},
        {"services", func() (interface{}, error) {
            return kubeClient.CoreV1().Services(namespace).List(ctx, metav1.ListOptions{})
        }},
        // Add more resource types as needed
    }

    for _, res := range resources {
        GinkgoWriter.Printf("  Removing finalizers from %s...\n", res.name)
        // Implementation to patch and remove finalizers
        removeFinalizersFromResourceType(namespace, res)
    }
}
```

## Rollout Strategy

### Phase 1: Apply to New Tests (Week 1)

1. **Update test template** with isolation patterns
2. **Document patterns** in CONTRIBUTING.md
3. **Apply to new tests** being written

**Success Criteria**:
- ✓ All new tests use unique namespaces
- ✓ All new tests have DeferCleanup

### Phase 2: Migrate High-Value Tests (Week 2-3)

Priority order:
1. **TestOdhOperator** - highest failure count
2. **Cluster install tests** - highest failure rate
3. **Component tests** - Dashboard, KServe, DSP, etc.

**Migration checklist per test**:
- [ ] Add unique namespace creation in BeforeEach
- [ ] Move resources to test namespace
- [ ] Add cleanup in AfterEach
- [ ] Test in isolation (run alone)
- [ ] Test in parallel (run with others)
- [ ] Verify cleanup completes

### Phase 3: Enable Parallel Execution (Week 4)

Once tests are properly isolated:

1. **Update Prow config** to run tests in parallel:
```yaml
# ci-operator config
tests:
  - as: e2e-test
    commands: make test-e2e GINKGO_ARGS="-p -procs=4"
```

2. **Monitor for issues**:
   - Resource exhaustion
   - Increased failure rates
   - Timeout issues

3. **Tune parallelism** based on results:
   - Start with `-procs=2`
   - Increase to `-procs=4` if stable
   - Don't exceed cluster capacity

## Expected Impact

### Before: Sequential Tests with Shared Resources

```
Test A (namespace: test)     → 15 min → Leaks resources
Test B (namespace: test)     → 10 min → Conflicts, fails
Test C (namespace: test)     → 12 min → Resource exhaustion, fails
Total: 37 min, 2 failures (cascading)
```

### After: Parallel Tests with Isolation

```
Test A (namespace: test-a-123) → 15 min → Clean cleanup
Test B (namespace: test-b-456) → 10 min → No conflicts
Test C (namespace: test-c-789) → 12 min → Independent
Total: 15 min (parallel), 0 cascading failures
```

**Improvements**:
- **Time**: 37 min → 15 min (60% faster)
- **Cascading failures**: 2 → 0 (eliminated)
- **Resource utilization**: Better (parallel execution)
- **Debuggability**: Easier (isolated failures)

## Monitoring

Track these metrics to measure improvement:

### Cascading Failure Rate

```sql
-- Tests that fail when previous test failed
WITH test_sequence AS (
    SELECT
        build_id,
        test_name,
        status,
        started_at,
        LAG(status) OVER (PARTITION BY build_id ORDER BY started_at) as prev_test_status
    FROM test_cases
)
SELECT
    COUNT(*) FILTER (WHERE status = 'failed' AND prev_test_status = 'failed') as cascading_failures,
    COUNT(*) FILTER (WHERE status = 'failed') as total_failures,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'failed' AND prev_test_status = 'failed') /
          COUNT(*) FILTER (WHERE status = 'failed'), 1) as cascading_pct
FROM test_sequence;
```

**Target**: < 10% cascading failures (from unknown baseline)

### Cleanup Success Rate

```sql
-- Namespaces that cleanup successfully
SELECT
    COUNT(*) FILTER (WHERE cleanup_duration < 120) as fast_cleanups,
    COUNT(*) FILTER (WHERE cleanup_duration >= 120) as slow_cleanups,
    COUNT(*) FILTER (WHERE cleanup_failed = true) as failed_cleanups,
    COUNT(*) as total_tests
FROM test_cleanup_metrics;
```

**Target**: > 95% fast cleanups (< 2 min), < 1% failed cleanups

### Resource Leak Detection

```sql
-- Namespaces left behind after tests
SELECT
    namespace,
    created_at,
    age_hours
FROM orphaned_namespaces
WHERE namespace LIKE 'test-%'
  AND age_hours > 24;
```

**Target**: 0 orphaned test namespaces older than 24 hours

## Related Documentation

- [Fail-Fast Patterns](fail-fast-patterns.md) - Add to BeforeEach with isolation
- [Test Improvements](../findings/test-improvements.md) - Test-specific fixes
- [Prow Test Suites](../prow/test-suites.md) - Test organization
- [Component Reliability](component-reliability.md) - Component-specific patterns
