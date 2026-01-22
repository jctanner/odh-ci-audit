# E2E Test Suites

## Overview

The opendatahub-operator e2e tests cover deployment and functionality of operator-managed components.

**Test Directory**: `tests/e2e/` in opendatahub-operator repo

**Framework**: Ginkgo + Gomega

**Execution**: Runs in Prow CI on every PR

## Test Suites

### Dashboard

**File**: `dashboard_test.go`

**Purpose**: Test ODH Dashboard UI deployment

**Tests**:

- Dashboard deployment creation
- Service and route configuration
- Pod readiness
- ConfigMap mounting

**Typical Duration**: 2-5 minutes

**Common Failures**:

- Image pull errors
- Timeout waiting for pod ready
- Route configuration issues

### Data Science Pipelines

**File**: `datasciencepipelines_test.go`

**Purpose**: Test Kubeflow Pipelines integration

**Tests**:

- DSP deployment and services
- MariaDB/MySQL database setup
- Minio object storage
- Pipeline execution

**Typical Duration**: 5-10 minutes

**Common Failures**:

- Database connection timeouts
- Persistent volume provisioning
- Service mesh integration issues

### KServe

**File**: `kserve_test.go`

**Purpose**: Test KServe model serving

**Tests**:

- KServe controller deployment
- Inference service creation
- Model serving runtime
- Serverless integration

**Typical Duration**: 5-10 minutes

**Common Failures**:

- Knative serving dependencies
- Istio gateway configuration
- Model storage access

### Model Registry

**File**: `modelregistry_test.go`

**Purpose**: Test ML model registry

**Tests**:

- Registry service deployment
- Database initialization
- Model metadata storage
- REST API access

**Typical Duration**: 3-7 minutes

**Common Failures**:

- Database schema migration
- Service exposure
- Persistent storage

### Kueue

**File**: `kueue_test.go`

**Purpose**: Test job queueing system

**Tests**:

- Kueue controller deployment
- Resource quota management
- Job queue creation
- Workload scheduling

**Typical Duration**: 3-5 minutes

**Common Failures**:

- CRD installation
- Webhook configuration
- Resource quota conflicts

### Gateway

**File**: `gateway_test.go`

**Purpose**: Test Istio gateway configuration

**Tests**:

- Gateway resource creation
- Virtual service routing
- TLS certificate management
- Ingress configuration

**Typical Duration**: 2-4 minutes

**Common Failures**:

- Istio dependencies
- Certificate provisioning
- Route conflicts

### Operator Tests

**Feast Operator**: `feastoperator_test.go`

- Feast feature store deployment
- Redis backend setup

**MLflow Operator**: `mlflowoperator_test.go`

- MLflow tracking server
- Artifact storage configuration

**LlamaStack Operator**: `llamastackoperator_test.go`

- LlamaStack deployment (newer addition)
- Model serving integration

## Test Execution

### Local Execution

```bash
# Run all e2e tests
make test-e2e

# Run specific suite
ginkgo -v -focus="Dashboard" tests/e2e/

# Run with retries for flake detection
ginkgo -v --flake-attempts=3 tests/e2e/
```

### CI Execution

```bash
# In ci-operator
test:
- as: e2e-test
  commands: make test-e2e
  from: src
```

## Test Organization

```go
// Typical test structure
var _ = Describe("Component", func() {
    Context("When component is deployed", func() {
        It("Should create required resources", func() {
            // Test implementation
        })

        It("Should be ready", func() {
            Eventually(checkPodReady, timeout).Should(Succeed())
        })
    })

    Context("When component is deleted", func() {
        It("Should cleanup resources", func() {
            // Cleanup verification
        })
    })
})
```

## Resource Requirements

**Per-test resources**:

- Namespace creation
- Operator deployment
- Component-specific resources (deployments, services, PVCs)
- Cleanup

**Cluster requirements**:

- CPU: 4-8 cores
- Memory: 16-32 GB
- Storage: 50-100 GB

## Test Timeouts

```go
const (
    timeout  = time.Second * 300  // 5 minutes
    interval = time.Second * 10   // Poll every 10s
)
```

**Common timeout values**:

- Pod ready: 2-5 minutes
- Deployment rollout: 3-10 minutes
- Operator reconciliation: 1-2 minutes
- Resource creation: 30-60 seconds

## Failure Categories

### Infrastructure

- Pod scheduling failures
- Image pull errors
- PVC provisioning timeouts
- Node resource exhaustion

### Timing

- Timeout waiting for pod ready
- Deployment not progressing
- Reconciliation loops

### Configuration

- Missing CRDs
- Invalid CR specs
- Webhook configuration errors

### Dependencies

- Missing prerequisite operators
- Service mesh not available
- Storage class not found

## JUnit Output Mapping

```
Test Suite → <testsuite name="...">
  Context → No direct mapping (logical grouping)
    It → <testcase name="..." classname="...">
```

**Example**:

```xml
<testsuite name="Dashboard">
  <testcase name="Should create deployment" classname="e2e.dashboard" time="12.34"/>
</testsuite>
```

## Findings

### Test Suite Failure Rate Statistics

From [Common Failures](../findings/common-failures.md), component-specific failure rates:

| Component | Total Tests | Failures | Passes | Failure Rate | Reliability |
|-----------|-------------|----------|--------|--------------|-------------|
| **Dashboard** | 51,379 | 295 | 51,084 | **0.6%** | **Highly reliable** |
| **DataSciencePipelines** | 118,831 | 710 | 118,121 | **0.6%** | **Highly reliable** |
| **ModelRegistry** | 35,708 | 243 | 35,465 | **0.7%** | **Highly reliable** |
| **KServe** | 41,108 | 658 | 40,450 | **1.6%** | Very reliable |
| **Kueue** | 40,982 | 846 | 40,136 | **2.1%** | Reliable |
| **Monitoring** | 81,772 | 3,151 | 78,621 | **3.9%** | Moderate |
| **Gateway** | 10,111 | 527 | 9,584 | **5.2%** | Moderate |
| **Trainer** | 19,428 | 1,904 | 17,524 | **9.8%** | **Least reliable** |

**Key Findings**:

1. **Dashboard, DSP, and ModelRegistry are most reliable** (< 1% failure rates) - contrary to expectations
2. **Trainer has highest failure rate** at 9.8% (1,904 failures)
3. **Most test volume**: DataSciencePipelines with 118,831 total executions
4. **Monitoring has most total failures** (3,151) but moderate rate (3.9%) due to high volume

### Test Duration Analysis

From [Duration Analysis](../analysis/duration/per-suite.md), component duration impact:

| Component | Test Volume | Failure Rate | Duration Impact |
|-----------|-------------|--------------|-----------------|
| **DataSciencePipelines** | 118,831 tests | 0.6% | **Highest cumulative time** (largest test count) |
| **Monitoring** | 81,772 tests | 3.9% | High cumulative time (large volume) |
| **Trainer** | 19,428 tests | 9.8% | **Most wasted time** (highest failure rate = more retries) |
| **Dashboard** | 51,379 tests | 0.6% | Moderate time, highly efficient |
| **KServe** | 41,108 tests | 1.6% | Moderate time, very efficient |

**Observations**:

- **Expected duration** (from file headers): 2-10 minutes per suite
- **Actual duration**: E2E jobs average 115.6 min total (all suites combined)
- **DataSciencePipelines**: Long cumulative time despite low failure rate due to sheer volume
- **Trainer**: More time wasted on retries due to 9.8% failure rate

### Flake Rate Per Suite

From [Common Failures](../findings/common-failures.md) and [Flake Rate Analysis](../findings/flake-rate.md), flake patterns by component:

| Component | Flake Pattern | Reality |
|-----------|---------------|---------|
| **Dashboard** | **100% failure rate when failing** | Not flaky - tests are consistently broken/disabled |
| **KServe** | **100% failure rate when failing** | Not flaky - tests are consistently broken/disabled |
| **DataSciencePipelines** | **100% failure rate when failing** | Not flaky - tests are consistently broken/disabled |
| **ModelRegistry** | **100% failure rate when failing** | Not flaky - tests are consistently broken/disabled |
| **Monitoring** | Mixed pass/fail patterns | Some flakiness present |
| **Gateway** | Mixed pass/fail patterns | Some flakiness present |
| **Trainer** | Mixed pass/fail patterns | Some flakiness present |

**Critical Insight**:

The highly reliable components (Dashboard, KServe, DSP, ModelRegistry) all show a **100% failure rate** pattern for their failing tests. This means:

- When these tests fail, they fail **consistently** (all attempts fail)
- **Not experiencing intermittent failures** (not flaky in the traditional sense)
- Likely test infrastructure setup issues or intentionally disabled tests
- Small minority of total failures (only 0.4% of all 39,117 failures)

**True flake sources** (from [Per-Test Breakdown](../analysis/failures/per-test.md)):

- **TestOdhOperator**: 81.5% failure rate (4,378 failures, 995 passes) - highly flaky
- **cluster install tests**: 91-93% failure rates - infrastructure provisioning flakes
- **TestOdhOperator hierarchy**: Parent and child tests all 60-90% flake rates
- **Operator status checks**: 90.9% flake rate - operators not ready in time

**Conclusion**: The **99.6% of failures are from flaky tests**, but it's NOT the component-specific tests (Dashboard, KServe, etc.) that are flaky - it's the **infrastructure and operator setup tests** (TestOdhOperator, cluster install) that cause nearly all flakiness.

## Related

- [Test Framework](test-framework.md)
- [Job Types](job-types.md)
- [GCS Artifacts](artifacts.md)
