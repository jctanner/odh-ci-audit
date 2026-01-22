# Configuration Issues

## Definition

Failures due to incorrect, missing, or invalid configuration.

## Characteristics

- YAML parsing errors
- Invalid resource specifications
- Missing environment variables
- Permission/RBAC errors
- Invalid field values

## Detection Patterns

```python
CONFIGURATION_PATTERNS = [
    r'invalid.*yaml',
    r'permission denied',
    r'forbidden',
    r'missing.*config',
    r'invalid configuration',
    r'parse.*error',
    r'unknown field',
    r'invalid.*value',
]
```

## Statistics

From [Common Failures](../../findings/common-failures.md) failure type distribution analysis:

**Configuration Failure Metrics** (from build log analysis of 4,193 failed builds):

| Failure Type | Count | % of Failures |
|--------------|-------|---------------|
| Infrastructure | 3,673 | 87.6% |
| **Configuration** | **514** | **12.3%** |
| Code Regression | 4 | 0.1% |
| Unknown/Other | 3 | 0.1% |

- **Total Configuration Failures**: 514 failures
- **Percentage of All Failures**: **12.3%**
- **Second most common failure type** after infrastructure issues

**Important Context**: While configuration issues represent 12.3% of failures, many of these may actually be infrastructure-related:
- YAML parsing errors could be due to corrupted files from storage issues
- Permission errors could be RBAC resources not ready yet (timing/infrastructure)
- Missing config could be ConfigMaps/Secrets not created due to pod startup failures

**Overlap with Infrastructure** (from [Infrastructure Issues](../../findings/infrastructure.md)):
- 51.3% of failures involve pod startup issues, which can manifest as "missing config" errors
- Infrastructure degradation can cause permission/RBAC failures when operators aren't ready
- The 12.3% configuration failures may include infrastructure-triggered issues that present as config errors

## Example Failures

Based on detection patterns used in [Common Failures](../../findings/common-failures.md) analysis for configuration issues (12.3% of failures):

**YAML Parsing Errors**:
```
Error: invalid YAML: error converting YAML to JSON: yaml: unmarshal errors:
  line 5: field spec.replica not found in type v1.Deployment

Error parsing YAML: found character that cannot start any token
  Invalid indentation in YAML file at line 12

Error: error validating data: ValidationError(Deployment.spec):
  unknown field "replicas" in io.k8s.api.apps.v1.DeploymentSpec
```

**Permission/RBAC Errors**:
```
Error: Forbidden: User "system:serviceaccount:test:default" cannot create
  resource "deployments" in API group "apps" in the namespace "test-ns"

Error: serviceaccounts "opendatahub-operator" is forbidden:
  User cannot create resource in namespace

Error: admission webhook denied the request: insufficient permissions
```

**Missing Configuration**:
```
Error: Missing required environment variable: DATABASE_URL

Error: ConfigMap "opendatahub-config" not found in namespace "opendatahub"

Error: Secret "webhook-server-cert" not found
  Required for webhook server startup

Error: failed to mount volume: referenced secret "pull-secret" not found
```

**Actual vs Expected** (from log pattern analysis):

These configuration patterns account for 514 failures (12.3%), but given:
- 87.6% of failures show infrastructure error patterns
- 51.3% of failures involve pod startup issues
- Same-SHA analysis shows 95% of failures aren't code-related

Many "configuration" failures may actually be infrastructure timing issues:
- ConfigMap not created yet → pod startup failure → infrastructure issue
- RBAC not ready → operator not reporting conditions → infrastructure issue
- Permission denied → webhook not available → infrastructure timing issue

## Common Causes

### YAML Errors

```yaml
# Bug: Typo in field name
spec:
  replica: 1  # Should be 'replicas'

# Bug: Invalid indentation
spec:
replicas: 1  # Should be indented

# Bug: Missing required field
spec:
  # Missing 'selector' field
  template:
    ...
```

### RBAC/Permissions

- ServiceAccount lacks required permissions
- ClusterRole not bound correctly
- Namespace-scoped resources vs. cluster-scoped
- API group/version mismatch

### Missing Configuration

- ConfigMap not created
- Secret not mounted
- Environment variable not set
- Volume mount missing

## Impact

- Quick to fix once identified
- Often caught early in CI
- May indicate configuration drift
- Documentation may need updates

## Mitigation

### Prevention

1. Schema validation in CI
2. `kubectl --dry-run=client` validation
3. CRD validation rules
4. Pre-submit YAML linting

### Testing

1. Dedicated config validation tests
2. Permission/RBAC tests
3. Negative test cases (invalid config)

### Development

1. Use typed config structs
2. Validation webhooks
3. Default values for optional fields
4. Clear error messages

## Query for Analysis

```sql
-- Configuration failures by message pattern
SELECT
    LEFT(failure_message, 80) as config_error,
    COUNT(*) as occurrences,
    COUNT(DISTINCT test_name) as affected_tests
FROM test_cases
WHERE status = 'failed'
  AND failure_type = 'configuration'
GROUP BY LEFT(failure_message, 80)
ORDER BY occurrences DESC
LIMIT 20;
```

## Related

- [Failure Classification](../failures/classification.md)
- [Test Suites](../../prow/test-suites.md)
