# Test-Specific Improvements

## Overview

Based on 6 months of failure data analysis, this document identifies specific tests that need fixes and provides actionable recommendations.

**Context**: While infrastructure improvements (auto-retry, fail-fast, capacity) will address 80-90% of failures, fixing the worst flaky tests is still important for long-term reliability.

## High-Priority Test Fixes

### Priority 1: TestOdhOperator (11.2% of ALL Failures)

**Data**:
- **4,378 failures** (11.2% of all 39,117 failures)
- **81.5% failure rate** (4,378 failures, 995 passes)
- **Root cause**: Infrastructure setup issues, not the operator code itself

**Current Behavior**:
```go
var _ = Describe("TestOdhOperator", func() {
    It("Should deploy and configure all components", func() {
        // Monolithic test that does everything:
        // 1. Deploy operator
        // 2. Create DSC
        // 3. Verify all components (dashboard, kserve, dsp, etc.)
        // 4. Run validation tests
        // 5. Cleanup

        // Problem: If step 1 fails, entire test fails
        // Problem: Takes 82 minutes on average
        // Problem: Cascading failures from infrastructure issues
    })
})
```

**Recommended Fix**: Split into independent, smaller tests

```go
var _ = Describe("TestOdhOperator", func() {
    // INFRASTRUCTURE CHECK (fail fast)
    BeforeEach(func() {
        By("Running pre-flight infrastructure check")
        err := InfrastructureHealthCheck(ctx)
        if err != nil {
            Skip(fmt.Sprintf("[INFRASTRUCTURE] %v", err))
        }
    })

    // TIER 1: Operator deployment (independent test)
    Context("Operator deployment", func() {
        It("Should deploy operator successfully", func() {
            deployOperator()
            verifyOperatorReady()
        })
    })

    // TIER 2: Component tests (run in parallel if possible)
    Context("Dashboard component", func() {
        It("Should deploy dashboard", func() {
            // Independent of other components
            deployDashboard()
            verifyDashboard()
        })
    })

    Context("KServe component", func() {
        It("Should deploy KServe", func() {
            // Independent of other components
            deployKServe()
            verifyKServe()
        })
    })

    // Repeat for each component...
})
```

**Expected Impact**:
- **Reduce cascading failures**: One component failure doesn't fail entire test
- **Better isolation**: Can identify which specific component has issues
- **Easier retries**: Retry just the failing component, not everything
- **Estimated reduction**: 4,378 failures → ~1,500 failures (65% reduction)

### Priority 2: Cluster Install Tests (91-93% Failure Rate)

**Data**:
- **cluster install: install should succeed: overall**: 372 failures, 33 passes (91.9% failure rate)
- **cluster install: install should succeed: other**: 372 failures, 29 passes (92.8% failure rate)
- **Root cause**: Cluster provisioning timeouts

**Current Behavior**:
```
Test starts → Provision cluster → Timeout after 20-30 min → Fail
```

**Recommended Fix**: Add provisioning health checks

```go
var _ = Describe("cluster install", func() {
    It("install should succeed", func() {
        // CHECK 1: Pre-provisioning health (fail fast)
        By("Checking pre-provisioning requirements")
        err := CheckProvisioningCapacity()
        if err != nil {
            Skip(fmt.Sprintf("[INFRASTRUCTURE] Cannot provision: %v", err))
        }

        // CHECK 2: Provision with timeout
        By("Provisioning cluster")
        cluster, err := ProvisionClusterWithTimeout(20 * time.Minute)
        if err != nil {
            // Classify error
            if IsTimeoutError(err) {
                Fail(fmt.Sprintf("[INFRASTRUCTURE] Provisioning timeout: %v", err))
            }
            Fail(fmt.Sprintf("Provisioning failed: %v", err))
        }

        // CHECK 3: Verify cluster health
        By("Verifying cluster health")
        Eventually(func() bool {
            return cluster.IsHealthy()
        }, 5*time.Minute, 30*time.Second).Should(BeTrue())
    })
})
```

**Additional Fix**: Separate provisioning from testing

```yaml
# Option: Pre-provision clusters (hot spares - see hot-spare-analysis.md)
# But NOT recommended until after other improvements (cost vs benefit)
```

**Expected Impact**:
- **Faster failure detection**: 5-10 min vs 20-30 min
- **Clear error messages**: "Cannot provision - quota exhausted" vs "timeout"
- **Estimated reduction**: 372 failures → ~100 failures (73% reduction)

### Priority 3: TestOdhOperator Hierarchy (60-65% Failure Rates)

**Data**:
- **TestOdhOperator/services**: 1,753 failures (62.5% failure rate)
- **TestOdhOperator/components**: 1,743 failures (54.9% failure rate)
- **TestOdhOperator/services/group_1**: 1,585 failures (65.0% failure rate)
- **TestOdhOperator/services/group_1/monitoring**: 1,399 failures (60.6% failure rate)

**Pattern**: Child tests inherit parent failures (cascading)

**Current Structure**:
```
TestOdhOperator (fails)
  ├─ services (inherits parent failure)
  │   └─ group_1 (inherits parent failure)
  │       └─ monitoring (inherits parent failure)
  └─ components (inherits parent failure)
```

**Recommended Fix**: Remove hierarchical dependencies

```go
// BEFORE: Nested contexts (dependencies)
var _ = Describe("TestOdhOperator", func() {
    Context("services", func() {
        // Parent must succeed for this to run
        Context("group_1", func() {
            // grandparent + parent must succeed
            It("monitoring", func() {
                // ...
            })
        })
    })
})

// AFTER: Flat structure (independent)
var _ = Describe("TestOdhOperator", func() {
    BeforeEach(func() {
        // Shared setup
        ensureOperatorDeployed()
    })

    It("Should deploy monitoring service", func() {
        // Independent test - doesn't depend on others
        deployMonitoring()
        verifyMonitoring()
    })

    It("Should deploy gateway service", func() {
        // Independent test
        deployGateway()
        verifyGateway()
    })

    // Each component gets its own independent test
})
```

**Expected Impact**:
- **Eliminate cascading failures**: 1,753 + 1,743 + 1,585 + 1,399 = 6,480 → ~2,000 (69% reduction)
- **Better parallelization**: Independent tests can run in parallel
- **Easier debugging**: Clear which specific service/component failed

## Moderate-Priority Fixes

### Fix Dashboard/KServe/DSP 100% Failure Rate Tests

**Data** (from [Common Failures](common-failures.md)):
- **Dashboard**: 295 failures with 100% failure rate when failing
- **KServe**: 658 failures with 100% failure rate when failing
- **DataSciencePipelines**: 710 failures with 100% failure rate when failing

**Pattern**: When these tests fail, they fail consistently (not flaky)

**Investigation Needed**:
1. Are these tests intentionally disabled?
2. Is test infrastructure missing prerequisites?
3. Are they running in wrong environment?

**Recommended Action**:
```bash
# For each 100% failure rate test:
1. Check if test is disabled/skipped in code
2. Check if test has missing prerequisites (CRDs, operators, etc.)
3. Run test locally to reproduce
4. Either:
   a) Fix the prerequisite issue, OR
   b) Formally skip/remove the test if no longer valid
```

**Expected Impact**:
- **Reduce noise**: 295 + 658 + 710 = 1,663 failures → 0 (eliminate or fix)
- **Clearer signals**: Remove consistently broken tests from failure counts

## Timeout Adjustments

See [Timeout Strategy](../recommendations/timeout-strategy.md) for comprehensive timeout recommendations.

### Per-Component Timeout Tuning

Based on actual duration data:

| Component | Current Timeout | Recommended | Rationale |
|-----------|----------------|-------------|-----------|
| Dashboard | Generic (10 min) | 15 min | Quick to deploy (avg 5-8 min) |
| ModelRegistry | Generic (10 min) | 15 min | Quick to deploy |
| KServe | Generic (10 min) | 30 min | Serverless dependencies are slow |
| DataSciencePipelines | Generic (10 min) | 40 min | Full stack (DB + Minio + Pipeline) |
| Monitoring | Generic (10 min) | 25 min | Prometheus + Grafana stack |
| Gateway | Generic (10 min) | 20 min | Istio dependencies |

**Implementation**:
```go
var componentTimeouts = map[string]time.Duration{
    "dashboard":            15 * time.Minute,
    "modelregistry":        15 * time.Minute,
    "kserve":               30 * time.Minute,
    "datasciencepipelines": 40 * time.Minute,
    "monitoring":           25 * time.Minute,
    "gateway":              20 * time.Minute,
}
```

## Resource Allocation

### Test Isolation & Cleanup

**Problem**: Tests don't clean up resources properly, leading to resource exhaustion.

**Recommended Fix**:
```go
var _ = Describe("Component tests", func() {
    var testNamespace string

    BeforeEach(func() {
        // Create unique namespace for this test
        testNamespace = fmt.Sprintf("test-%s-%d", testName, time.Now().Unix())
        createNamespace(testNamespace)
    })

    AfterEach(func() {
        // ALWAYS cleanup, even on failure
        By("Cleaning up test namespace")
        deleteNamespace(testNamespace)

        // Wait for cleanup to complete
        Eventually(func() bool {
            return namespaceDeleted(testNamespace)
        }, 2*time.Minute, 5*time.Second).Should(BeTrue())
    })

    It("Should deploy component", func() {
        // Test runs in isolated namespace
        deployComponent(testNamespace)
    })
})
```

### Resource Requests & Limits

**Problem**: Tests compete for resources without guarantees.

**Recommended Fix**: Add resource requests to test pods

```yaml
# In ci-operator config
resources:
  requests:
    cpu: "2"
    memory: "4Gi"
  limits:
    cpu: "4"
    memory: "8Gi"
```

## Code Quality Issues

### Pattern 1: No Retry Logic in Tests

**Current**: Tests give up immediately on transient failures

```go
// BEFORE: Fail immediately
pod := getPod()
if !pod.IsReady() {
    Fail("Pod not ready")
}
```

**Recommended**: Use Eventually for operations that might take time

```go
// AFTER: Retry with timeout
Eventually(func() bool {
    pod := getPod()
    return pod.IsReady()
}, 5*time.Minute, 10*time.Second).Should(BeTrue())
```

### Pattern 2: Poor Error Messages

**Current**: Generic error messages don't help debugging

```go
Expect(err).NotTo(HaveOccurred())
// Error: expected no error but got: <error>
```

**Recommended**: Provide context in error messages

```go
Expect(err).NotTo(HaveOccurred(), "Failed to deploy dashboard in namespace %s", namespace)
// Error: Failed to deploy dashboard in namespace test-12345: <error details>
```

### Pattern 3: Missing Cleanup

**Current**: Tests leak resources on failure

```go
It("Should work", func() {
    createResource()
    // If test fails here, resource is leaked
    verifyResource()
})
```

**Recommended**: Use DeferCleanup

```go
It("Should work", func() {
    resource := createResource()
    DeferCleanup(func() {
        deleteResource(resource)
    })

    verifyResource()
    // Cleanup happens even if test fails
})
```

## Implementation Priority

Tackle in this order for maximum impact:

1. **Week 1-2**: Split TestOdhOperator (Priority 1) - saves 2,878 failures (7.4%)
2. **Week 3-4**: Fix cluster install tests (Priority 2) - saves 272 failures (0.7%)
3. **Week 5-6**: Flatten TestOdhOperator hierarchy (Priority 3) - saves 4,480 failures (11.5%)
4. **Week 7-8**: Investigate 100% failure rate tests - eliminate 1,663 failures (4.3%)
5. **Week 9+**: Apply patterns (cleanup, error messages, etc.) to remaining tests

**Total Potential Impact**: Reduce failures from 39,117 → ~24,000 (39% reduction)

**Combined with infrastructure improvements**: Could achieve 85%+ success rate.

## Related Documentation

- [Fail-Fast Patterns](../recommendations/fail-fast-patterns.md) - Add to all tests
- [Timeout Strategy](../recommendations/timeout-strategy.md) - Per-component tuning
- [Auto-Retry Configuration](../recommendations/auto-retry-configuration.md) - Handle remaining flakes
- [Flake Rate Analysis](flake-rate.md) - Data source
- [Common Failures](common-failures.md) - Test-specific data
