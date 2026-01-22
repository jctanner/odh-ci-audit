# Test Framework (Ginkgo/Gomega)

## Overview

The opendatahub-operator uses Ginkgo and Gomega for e2e testing.

- **Ginkgo**: BDD-style Go testing framework
- **Gomega**: Matcher/assertion library
- **Kubernetes**: Test target (operator on OpenShift)

## Ginkgo Framework

### Test Structure

```go
// e2e test structure
var _ = Describe("Dashboard", func() {
    Context("When deploying Dashboard component", func() {
        It("Should create Dashboard deployment", func() {
            Eventually(func() error {
                deployment := &appsv1.Deployment{}
                return k8sClient.Get(ctx, deploymentKey, deployment)
            }, timeout, interval).Should(Succeed())
        })
    })
})
```

### Test Organization

```
tests/
  e2e/
    dashboard_test.go
    datasciencepipelines_test.go
    kserve_test.go
    modelregistry_test.go
    ...
```

### Execution

```bash
# Run all e2e tests
ginkgo -v -p tests/e2e/

# Run specific test
ginkgo -v -focus="Dashboard" tests/e2e/
```

## Gomega Matchers

Common assertions used in tests:

```go
// Success matchers
Expect(err).Should(Succeed())
Expect(err).ShouldNot(HaveOccurred())

// Equality
Expect(deployment.Status.ReadyReplicas).Should(Equal(int32(1)))

// Eventual consistency (common in K8s tests)
Eventually(func() int {
    return deployment.Status.ReadyReplicas
}, timeout, interval).Should(Equal(int32(1)))

// String matchers
Expect(pod.Status.Phase).Should(Equal(corev1.PodRunning))
Expect(logOutput).Should(ContainSubstring("Reconciliation complete"))
```

## JUnit XML Output

Ginkgo generates JUnit XML for CI integration:

```bash
# Generate JUnit report
ginkgo -v --junit-report=junit.xml tests/e2e/
```

**Output Structure**:

```xml
<testsuite name="e2e suite" tests="25" failures="2" time="1234.56">
  <testcase name="Dashboard Should create deployment" classname="e2e.dashboard" time="12.34">
  </testcase>
  <testcase name="Kserve Should fail to deploy" classname="e2e.kserve" time="45.67">
    <failure message="Expected pod to be running" type="assertion">
      Expected success, but got:
        error creating Kserve deployment: timeout waiting for pod
    </failure>
  </testcase>
</testsuite>
```

## Test Suites in opendatahub-operator

**Component Tests**: Each operator component has dedicated tests

- `dashboard_test.go`: Dashboard UI deployment
- `datasciencepipelines_test.go`: Kubeflow Pipelines integration
- `kserve_test.go`: KServe model serving
- `modelregistry_test.go`: Model registry
- `kueue_test.go`: Job queueing
- `gateway_test.go`: Istio gateway configuration

**Operator Tests**: Feast, MLflow, LlamaStack operators

## Test Execution Flow

```
1. Setup: Deploy operator, create namespace
2. Test: Deploy component, verify resources
3. Assert: Check pods running, services created
4. Cleanup: Delete resources, namespace
```

### Timeouts

```go
const (
    timeout  = time.Second * 300  // 5 minutes
    interval = time.Second * 10   // Poll every 10s
)
```

**Common timeouts**:

- Pod ready: 2-5 minutes
- Deployment ready: 3-10 minutes
- Operator reconciliation: 1-2 minutes

## Failure Scenarios

### Assertion Failures

```
Expected success, but got:
  <*errors.StatusError | 0xc0001234>
  pods "dashboard-xyz" not found
```

### Timeout Failures

```
Timed out after 300.00s.
Expected <int>: 1 to equal <int>: 0
```

### Panic Failures

```
panic: runtime error: invalid memory address or nil pointer dereference
```

## Flaky Test Detection

Ginkgo supports retries for flaky tests:

```go
// Retry failed tests
ginkgo -v --flake-attempts=3 tests/e2e/
```

**Flake indicators**:

- Passes on retry
- Timeout-related failures
- Race condition errors

## Related

- [Prow Architecture](architecture.md)
- [Job Types](job-types.md)
- [Test Suites](test-suites.md)

## External Links

- [Ginkgo Documentation](https://onsi.github.io/ginkgo/)
- [Gomega Matchers](https://onsi.github.io/gomega/)
- [Kubernetes Testing Guide](https://kubernetes.io/blog/2019/03/22/kubernetes-end-to-end-testing-for-everyone/)
