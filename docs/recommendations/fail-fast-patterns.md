# Fail-Fast Infrastructure Detection

## Problem Statement

### Current Behavior

E2E tests currently run for 90+ minutes before timing out when infrastructure is degraded, wasting compute time and providing slow, ambiguous feedback to developers.

**Data from CI Audit** (6-month period, July 2025 - January 2026):

| Metric | Current State | Impact |
|--------|---------------|--------|
| Average failed test duration | **92.0 minutes** | Tests run until timeout even when infrastructure is broken |
| Time wasted on infrastructure failures | **4,319 hours** (180 days) | 69.5% of failures involve timeouts |
| Infrastructure failure rate | **87.6%** | Most failures are NOT code issues |
| Developer experience | **75.4% of PRs** require manual `/retest` | Average 4.8 retries per PR |

**Specific failure pattern**:

```
00:00 - Test starts
00:01 - Infrastructure is already degraded (no available resources)
00:05 - First pod timeout (can't schedule)
00:15 - Second pod timeout
00:30 - Deployment timeout
00:45 - Operator reconciliation timeout
01:32 - Test finally times out and fails
```

**Result**: 92 minutes wasted, ambiguous error message "Test timed out", developer doesn't know if it's their code or infrastructure.

### Root Causes

From [Infrastructure Issues](../findings/infrastructure.md) and [CI Pipeline Issues](../findings/ci-pipeline.md):

1. **No pre-flight checks**: Tests don't verify infrastructure health before running
2. **Long timeouts**: Each operation waits 5-10 minutes before giving up
3. **No circuit breakers**: Tests retry operations even when cluster is clearly degraded
4. **Cascade failures**: One infrastructure issue triggers many timeout failures

## Solution: Fail-Fast Infrastructure Health Checks

### Core Principle

**Check infrastructure health BEFORE running expensive tests. Fail in < 5 minutes if infrastructure is degraded.**

Benefits:
- **Faster feedback**: Developer knows in 1-5 minutes that infrastructure is down (not their code)
- **Less wasted compute**: Save 2,800 hours/year (projected from data)
- **Clearer signals**: "Infrastructure unavailable" vs "Test timed out"
- **Better retry strategy**: Auto-retry can distinguish infrastructure vs code failures

### Expected Impact

| Metric | Current | With Fail-Fast | Improvement |
|--------|---------|----------------|-------------|
| Time to detect infrastructure failure | 92 min avg | < 5 min | **87 min saved per failure** |
| Wasted CI hours (6 months) | 4,319 hours | ~1,500 hours | **2,800 hours saved** |
| Developer clarity | Ambiguous timeout | "Infrastructure degraded" | Clear root cause |
| Auto-retry effectiveness | N/A | Can retry infrastructure failures only | Reduce manual retries by 70-80% |

## Implementation Patterns

### Pattern 1: Pre-Flight Infrastructure Check

Add a quick health check before running expensive tests.

```go
package e2e_test

import (
    "context"
    "time"

    . "github.com/onsi/ginkgo/v2"
    . "github.com/onsi/gomega"
    corev1 "k8s.io/api/core/v1"
    "k8s.io/apimachinery/pkg/api/resource"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// InfrastructureHealthCheck runs quick checks to verify cluster is ready
// Returns error if infrastructure is degraded, allowing test to fail fast
func InfrastructureHealthCheck(ctx context.Context) error {
    timeout := 30 * time.Second

    // Check 1: Cluster nodes are ready (5 seconds)
    GinkgoWriter.Printf("Pre-flight check: Verifying nodes are ready...\n")
    nodes, err := kubeClient.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
    if err != nil {
        return fmt.Errorf("failed to list nodes: %w", err)
    }

    readyNodes := 0
    for _, node := range nodes.Items {
        for _, condition := range node.Status.Conditions {
            if condition.Type == corev1.NodeReady && condition.Status == corev1.ConditionTrue {
                readyNodes++
                break
            }
        }
    }

    if readyNodes == 0 {
        return fmt.Errorf("no nodes are ready (%d total nodes)", len(nodes.Items))
    }

    GinkgoWriter.Printf("✓ %d/%d nodes ready\n", readyNodes, len(nodes.Items))

    // Check 2: Sufficient cluster resources available (5 seconds)
    GinkgoWriter.Printf("Pre-flight check: Verifying cluster resources...\n")
    totalCPU := resource.NewQuantity(0, resource.DecimalSI)
    totalMemory := resource.NewQuantity(0, resource.BinarySI)
    allocatableCPU := resource.NewQuantity(0, resource.DecimalSI)
    allocatableMemory := resource.NewQuantity(0, resource.BinarySI)

    for _, node := range nodes.Items {
        if cpu, ok := node.Status.Capacity[corev1.ResourceCPU]; ok {
            totalCPU.Add(cpu)
        }
        if mem, ok := node.Status.Capacity[corev1.ResourceMemory]; ok {
            totalMemory.Add(mem)
        }
        if cpu, ok := node.Status.Allocatable[corev1.ResourceCPU]; ok {
            allocatableCPU.Add(cpu)
        }
        if mem, ok := node.Status.Allocatable[corev1.ResourceMemory]; ok {
            allocatableMemory.Add(mem)
        }
    }

    // Require at least 20% of cluster capacity available
    minRequiredCPU := totalCPU.Value() * 20 / 100
    minRequiredMemory := totalMemory.Value() * 20 / 100

    if allocatableCPU.Value() < minRequiredCPU {
        return fmt.Errorf("insufficient CPU available: %d/%d cores (need 20%%)",
            allocatableCPU.Value(), totalCPU.Value())
    }

    if allocatableMemory.Value() < minRequiredMemory {
        return fmt.Errorf("insufficient memory available: %dGi/%dGi (need 20%%)",
            allocatableMemory.Value()/(1024*1024*1024),
            totalMemory.Value()/(1024*1024*1024))
    }

    GinkgoWriter.Printf("✓ Cluster resources available: %d cores, %dGi memory\n",
        allocatableCPU.Value(), allocatableMemory.Value()/(1024*1024*1024))

    // Check 3: Image registry is accessible (10 seconds)
    GinkgoWriter.Printf("Pre-flight check: Verifying image registry...\n")
    testPod := &corev1.Pod{
        ObjectMeta: metav1.ObjectMeta{
            Name:      "registry-health-check",
            Namespace: "default",
        },
        Spec: corev1.PodSpec{
            Containers: []corev1.Container{{
                Name:  "test",
                Image: "registry.redhat.io/ubi8/ubi-minimal:latest",
                Command: []string{"echo", "ok"},
            }},
            RestartPolicy: corev1.RestartPolicyNever,
        },
    }

    _, err = kubeClient.CoreV1().Pods("default").Create(ctx, testPod, metav1.CreateOptions{})
    if err != nil {
        return fmt.Errorf("failed to create registry test pod: %w", err)
    }
    defer kubeClient.CoreV1().Pods("default").Delete(ctx, testPod.Name, metav1.DeleteOptions{})

    // Wait up to 30 seconds for image pull to start
    Eventually(func() bool {
        pod, err := kubeClient.CoreV1().Pods("default").Get(ctx, testPod.Name, metav1.GetOptions{})
        if err != nil {
            return false
        }
        // Check if image pull has started (not stuck in ImagePullBackOff)
        for _, status := range pod.Status.ContainerStatuses {
            if status.State.Waiting != nil &&
               (status.State.Waiting.Reason == "ImagePullBackOff" ||
                status.State.Waiting.Reason == "ErrImagePull") {
                return false
            }
        }
        return true
    }, 30*time.Second, 2*time.Second).Should(BeTrue())

    GinkgoWriter.Printf("✓ Image registry accessible\n")

    // Check 4: Required operators are running (5 seconds)
    GinkgoWriter.Printf("Pre-flight check: Verifying required operators...\n")
    requiredOperators := []string{
        "opendatahub-operator-controller-manager",
    }

    for _, operatorName := range requiredOperators {
        deployment, err := kubeClient.AppsV1().Deployments("opendatahub").Get(
            ctx, operatorName, metav1.GetOptions{})
        if err != nil {
            return fmt.Errorf("required operator %s not found: %w", operatorName, err)
        }

        if deployment.Status.ReadyReplicas == 0 {
            return fmt.Errorf("required operator %s has no ready replicas", operatorName)
        }
    }

    GinkgoWriter.Printf("✓ Required operators running\n")

    GinkgoWriter.Printf("✓ All pre-flight checks passed - infrastructure healthy\n")
    return nil
}
```

### Pattern 2: Integration with Ginkgo Test Suite

Add infrastructure check to test suite setup:

```go
var _ = Describe("TestOdhOperator", func() {
    var ctx context.Context

    BeforeEach(func() {
        ctx = context.Background()

        // FAIL FAST: Check infrastructure before running expensive tests
        By("Verifying infrastructure health")
        err := InfrastructureHealthCheck(ctx)
        if err != nil {
            // Skip test with clear message
            Skip(fmt.Sprintf("Infrastructure not ready: %v", err))

            // OR fail fast with infrastructure label
            // Fail(fmt.Sprintf("[INFRASTRUCTURE] Cluster degraded: %v", err))
        }
    })

    Context("When components are deployed", func() {
        It("Should create Dashboard deployment", func() {
            // Test implementation
            // Now we know infrastructure is healthy!
        })

        It("Should create KServe resources", func() {
            // Test implementation
        })
    })
})
```

### Pattern 3: Circuit Breaker for Retry Operations

Don't retry operations when infrastructure is clearly failing:

```go
// WaitForPodReady waits for pod with circuit breaker
func WaitForPodReady(ctx context.Context, namespace, name string, timeout time.Duration) error {
    consecutiveFailures := 0
    maxConsecutiveFailures := 3

    return wait.PollImmediate(10*time.Second, timeout, func() (bool, error) {
        pod, err := kubeClient.CoreV1().Pods(namespace).Get(ctx, name, metav1.GetOptions{})
        if err != nil {
            consecutiveFailures++

            // Circuit breaker: If we fail 3 times in a row, check infrastructure
            if consecutiveFailures >= maxConsecutiveFailures {
                GinkgoWriter.Printf("⚠ Multiple consecutive failures - checking infrastructure...\n")

                if infraErr := InfrastructureHealthCheck(ctx); infraErr != nil {
                    // Infrastructure is degraded - fail fast instead of continuing to retry
                    return false, fmt.Errorf("infrastructure degraded, aborting retry: %w", infraErr)
                }

                // Infrastructure is OK, reset counter and continue
                consecutiveFailures = 0
            }

            return false, nil
        }

        // Check pod status
        for _, condition := range pod.Status.Conditions {
            if condition.Type == corev1.PodReady && condition.Status == corev1.ConditionTrue {
                return true, nil
            }
        }

        return false, nil
    })
}
```

### Pattern 4: Timeout Reduction with Early Exit

Reduce individual operation timeouts, fail fast on first sign of trouble:

```go
// OLD: Long timeout, wait 10 minutes
Eventually(func() bool {
    return deployment.IsReady()
}, 10*time.Minute, 10*time.Second).Should(BeTrue())

// NEW: Shorter timeout with infrastructure check on failure
timeout := 3 * time.Minute  // Reduced from 10 min
err := Eventually(func() bool {
    return deployment.IsReady()
}, timeout, 10*time.Second).Should(BeTrue())

if err != nil {
    // Failed - check if it's infrastructure before retrying
    if infraErr := InfrastructureHealthCheck(ctx); infraErr != nil {
        Fail(fmt.Sprintf("[INFRASTRUCTURE] Deployment not ready due to cluster issues: %v", infraErr))
    }
    // Not infrastructure - this is a real failure
    Fail(fmt.Sprintf("Deployment not ready: %v", err))
}
```

## Real Test Case Example

### Before (Current)

```go
var _ = Describe("TestOdhOperator", func() {
    It("Should deploy and configure components", func() {
        By("Creating namespace")
        namespace := createNamespace()  // Might timeout if no resources

        By("Deploying operator")
        deployOperator(namespace)  // Waits 10 minutes, might timeout

        By("Creating DSC")
        createDataScienceCluster(namespace)  // Waits 10 minutes, might timeout

        By("Verifying Dashboard")
        verifyDashboard(namespace)  // Waits 5 minutes, might timeout

        By("Verifying KServe")
        verifyKServe(namespace)  // Waits 5 minutes, might timeout

        // Total: Can run 40+ minutes before finally timing out
        // Error message: "Test timed out" (ambiguous)
    })
})
```

**Problem**: If cluster is out of resources at minute 1, test still runs for 40+ minutes hitting timeout after timeout.

### After (With Fail-Fast)

```go
var _ = Describe("TestOdhOperator", func() {
    var ctx context.Context

    BeforeEach(func() {
        ctx = context.Background()

        // FAIL FAST: Pre-flight check (30 seconds)
        By("Running pre-flight infrastructure check")
        err := InfrastructureHealthCheck(ctx)
        if err != nil {
            Skip(fmt.Sprintf("[INFRASTRUCTURE] Cluster not ready: %v", err))
        }
        GinkgoWriter.Printf("✓ Infrastructure healthy - proceeding with test\n")
    })

    It("Should deploy and configure components", func() {
        By("Creating namespace")
        namespace := createNamespace()

        By("Deploying operator")
        err := deployOperatorWithTimeout(namespace, 5*time.Minute)  // Reduced timeout
        if err != nil {
            // Check infrastructure before failing
            if infraErr := InfrastructureHealthCheck(ctx); infraErr != nil {
                Fail(fmt.Sprintf("[INFRASTRUCTURE] Operator deploy failed due to: %v", infraErr))
            }
            Fail(fmt.Sprintf("Operator deploy failed: %v", err))
        }

        By("Creating DSC")
        createDataScienceCluster(namespace)

        By("Verifying Dashboard")
        verifyDashboard(namespace)

        By("Verifying KServe")
        verifyKServe(namespace)

        // Total: Fails in < 5 minutes if infrastructure is bad
        // Error message: "[INFRASTRUCTURE] Cluster not ready: insufficient CPU available"
    })
})
```

**Result**: Infrastructure failure detected in 30 seconds, test skipped/failed with clear message.

## Rollout Strategy

### Phase 1: Add Health Checks to High-Value Tests (Week 1-2)

Target tests that fail most frequently and waste most time:

1. **TestOdhOperator** (81.5% failure rate, 4,378 failures)
2. **Cluster install tests** (91-93% failure rate)
3. **TestOdhOperator hierarchy** (services, components, monitoring)

**Expected impact**: Reduce wasted time by ~60% (2,600 hours → 1,000 hours)

### Phase 2: Add to All E2E Tests (Week 3-4)

Roll out to all e2e test suites:
- Dashboard tests
- DataSciencePipelines tests
- KServe tests
- ModelRegistry tests
- All component tests

**Expected impact**: Reduce wasted time by ~80% (2,600 hours → 500 hours)

### Phase 3: Integrate with Prow Auto-Retry (Week 5-6)

Configure Prow to automatically retry tests that fail with `[INFRASTRUCTURE]` prefix:

```yaml
presubmits:
  opendatahub-io/opendatahub-operator:
    - name: pull-ci-opendatahub-operator-e2e
      # Auto-retry infrastructure failures
      retry_on:
        - infrastructure_failure  # Custom label from fail-fast checks
      max_retries: 2
```

**Expected impact**:
- Reduce manual `/retest` commands by 70-80% (3,000 → 600)
- Better developer experience
- Clear distinction between code vs infrastructure failures

## Monitoring and Success Metrics

### Metrics to Track

1. **Time to first failure**:
   - Before: 92 min avg
   - Target: < 5 min for infrastructure failures

2. **Infrastructure failure detection rate**:
   - Before: 0% (all show as "test timeout")
   - Target: > 90% (clear "[INFRASTRUCTURE]" label)

3. **Wasted CI hours per month**:
   - Before: 720 hours/month (4,319 hours / 6 months)
   - Target: < 250 hours/month (65% reduction)

4. **Developer retry burden**:
   - Before: 75.4% of PRs need manual `/retest`
   - Target: < 30% need manual retry (rest auto-retry infrastructure failures)

### Dashboard

Add to Prow dashboard:
- Infrastructure health status (red/yellow/green)
- Time saved by fail-fast (cumulative)
- Infrastructure failure rate by hour (correlate with peak usage)
- Auto-retry success rate

## Related Documentation

- [Infrastructure Issues](../findings/infrastructure.md) - Root cause data
- [CI Pipeline Issues](../findings/ci-pipeline.md) - Recommendations context
- [Time Cost Analysis](../findings/time-cost.md) - Wasted compute metrics
- [Test Suites](../prow/test-suites.md) - E2E test organization
- [Job Types](../prow/job-types.md) - Job duration data
