# Dependency Failures

## Definition

Failures caused by missing, incompatible, or broken external dependencies.

## Characteristics

- CRD not found
- Required operator not installed
- API version not available
- Webhook failures
- Missing prerequisite resources

## Detection Patterns

```python
DEPENDENCY_PATTERNS = [
    r'crd.*not found',
    r'no matches for kind',
    r'operator.*not found',
    r'webhook.*failed',
    r'api version.*not found',
    r'resource.*does not exist',
    r'prerequisite.*missing',
]
```

## Statistics

From [Common Failures](../../findings/common-failures.md) analysis of failure messages:

**Dependency-Related Failures**:

The most specific dependency failure identified in the top failure messages:

| Failure Message | Occurrences | Affected Tests | % of Total |
|-----------------|-------------|----------------|------------|
| **Operator unavailable (null): operator is not reporting conditions** | **330** | **34** | **0.8%** |

**Analysis**:

- This is the only specific error message in the top 20 failures (others are generic "Test X failed")
- Affects 34 different tests (broad impact)
- Indicates operators/dependencies not ready when tests check their status
- **Categorization challenge**: This could be:
    - Infrastructure (operator pods not starting in time - 51.3% of failures involve pod startup)
    - Dependency (required operator not available)
    - The distinction is timing-based: Is the operator missing, or just not ready yet?

**Dependency Failures are Likely Subsumed by Other Categories**:

From the failure type breakdown (4,193 failed builds):

| Failure Type | Count | % | Likely Includes Dependency Issues |
|--------------|-------|---|-----------------------------------|
| **Infrastructure** | 3,673 | 87.6% | Operators not ready, pod startup delays |
| **Configuration** | 514 | 12.3% | CRDs not installed, missing resources |
| Code Regression | 4 | 0.1% | - |

**Key Insight**: True dependency failures (CRD not found, operator not installed) would appear in:
1. **Infrastructure category** if it's timing-related (operator installing but not ready)
2. **Configuration category** if it's truly missing (CRD never installed)

The "operator unavailable" error (330 occurrences) suggests timing/infrastructure issues rather than missing dependencies.

## Example Failures

**Actual Dependency Error** (from [Common Failures](../../findings/common-failures.md) top failure messages):

```
Operator unavailable (null): operator is not reporting conditions
  (330 occurrences across 34 different tests)
```

This is the most common specific dependency-related error in the dataset, indicating operators aren't ready when tests check their status.

**Expected Dependency Errors** (based on detection patterns):

```
Error: the server could not find the requested resource
  (get inferenceservices.serving.kserve.io)
  CRD not installed or not ready

Error: no matches for kind "ServiceMeshMember" in version "maistra.io/v1"
  Service mesh operator CRDs not available

Error: failed to call webhook "validator.kserve.io"
  dial tcp: lookup validator.kserve.io: no such host
  Webhook service not available
```

**Overlap with Infrastructure Failures**:

Many "dependency" failures are actually infrastructure timing issues:

```
Operator unavailable → pod not ready (51.3% of failures involve pod startup)
CRD not found → CRD installation timeout (69.5% involve timeouts)
Webhook failed → network issues (11.2% involve network errors)
```

From [Infrastructure Issues](../../findings/infrastructure.md):
- **51.3% of failures** involve pod startup issues
- **69.5% of failures** involve timeout errors
- Operators and CRDs depend on pod startup and timeout thresholds

**Reality**: Most "operator unavailable" errors are likely:
1. Operator pod hasn't started yet (infrastructure/timing)
2. Operator started but not reporting conditions yet (infrastructure/timing)
3. Operator actually missing (true dependency issue) - rare

This is supported by the fact that 87.6% of failures show infrastructure error patterns.

## Common Dependencies

### Operators

- KServe operator
- Service Mesh operator (Istio)
- Serverless operator (Knative)
- Kueue operator
- Storage operator

### CRDs

- InferenceService (KServe)
- ServiceMeshMember (Istio)
- KnativeServing (Serverless)
- Queue (Kueue)

### System Components

- cert-manager
- Ingress controller
- Storage provisioner
- Network policy provider

## Root Causes

### Installation Order

```yaml
# Bug: KServe deployed before CRDs installed
- name: Deploy KServe
  # Fails if CRDs not ready

# Fix: Ensure CRDs exist first
- name: Wait for KServe CRDs
  until: kserve_crds_ready
- name: Deploy KServe
```

### Version Incompatibility

- API version mismatch (v1alpha1 vs. v1beta1)
- Deprecated API removal
- Breaking changes in dependency

### Missing Namespace

- Resource in wrong namespace
- Namespace not created
- Cross-namespace references broken

## Impact

- Blocks dependent component tests
- May cascade to multiple tests
- Often requires env/cluster fixes
- Can indicate missing documentation

## Mitigation

### CI Environment

1. Pre-install all required operators
2. Wait for CRDs to be ready
3. Validate dependencies before tests
4. Document required components

### Testing

1. Dependency check tests
2. Fail fast on missing deps
3. Clear error messages
4. Prerequisite validation

### Code

1. Check API availability before use
2. Graceful degradation if optional dep missing
3. Version compatibility matrix

## Dependency Graph

```
opendatahub-operator
  ├── KServe
  │   ├── Knative Serving
  │   │   └── Istio
  │   └── cert-manager
  ├── Data Science Pipelines
  │   ├── Argo Workflows
  │   └── MariaDB operator
  └── Model Registry
      └── PostgreSQL operator
```

## Query for Analysis

```sql
-- Dependency failures by missing resource
SELECT
    SUBSTRING(failure_message FROM 'kind "([^"]+)"') as missing_kind,
    SUBSTRING(failure_message FROM 'version "([^"]+)"') as missing_version,
    COUNT(*) as occurrences,
    COUNT(DISTINCT test_name) as affected_tests
FROM test_cases
WHERE status = 'failed'
  AND failure_type = 'dependency'
  AND failure_message LIKE '%no matches for kind%'
GROUP BY missing_kind, missing_version
ORDER BY occurrences DESC;
```

## Related

- [Failure Classification](../failures/classification.md)
- [Test Suites](../../prow/test-suites.md)
- [Prow Architecture](../../prow/architecture.md)
