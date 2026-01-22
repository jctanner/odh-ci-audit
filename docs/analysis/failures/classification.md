# Failure Classification Methodology

## Overview

Systematic approach to categorizing test failures for root cause analysis.

## Failure Categories

### 1. Infrastructure Failures

**Definition**: Failures due to cluster/platform issues, not code bugs.

**Indicators**:

- Timeout waiting for resources
- Image pull errors
- Network connectivity issues
- Node resource exhaustion
- Pod scheduling failures

**Patterns**:

```python
INFRASTRUCTURE_PATTERNS = [
    r'timeout waiting for pod',
    r'image pull.*failed',
    r'context deadline exceeded',
    r'connection refused',
    r'no space left on device',
    r'failed to pull image',
    r'node not found',
    r'insufficient.*resources',
]
```

### 2. Test Flakes

**Definition**: Tests that fail intermittently without code changes.

**Indicators**:

- Passes on retry
- Timing-related failures
- "Eventually" timeout errors
- Race condition messages

**Patterns**:

```python
FLAKE_PATTERNS = [
    r'Eventually timed out',
    r'Consistently',
    r'race detected',
    r'timeout.*waiting',
    r'flake',
]
```

**Detection**: Test fails, then passes on same commit.

### 3. Code Regressions

**Definition**: Failures caused by bugs in PR code.

**Indicators**:

- Assertion failures
- Panic/nil pointer errors
- Expected vs. actual mismatches
- Logic errors

**Patterns**:

```python
REGRESSION_PATTERNS = [
    r'Expected.*but got',
    r'panic:',
    r'nil pointer dereference',
    r'assertion failed',
    r'test.*failed',
]
```

### 4. Configuration Issues

**Definition**: Incorrect or missing configuration.

**Indicators**:

- Invalid YAML
- Missing environment variables
- Permission denied
- Invalid resource specs

**Patterns**:

```python
CONFIGURATION_PATTERNS = [
    r'invalid.*yaml',
    r'permission denied',
    r'forbidden',
    r'missing.*config',
    r'invalid configuration',
]
```

### 5. Dependency Failures

**Definition**: Missing or incompatible dependencies.

**Indicators**:

- CRD not found
- Operator not installed
- Webhook unavailable
- API version mismatch

**Patterns**:

```python
DEPENDENCY_PATTERNS = [
    r'crd.*not found',
    r'no matches for kind',
    r'operator.*not found',
    r'webhook.*failed',
    r'api version.*not found',
]
```

### 6. Environment Issues

**Definition**: Cluster state or resource contention problems.

**Indicators**:

- Resource quotas exceeded
- Namespace conflicts
- Cluster instability
- Storage issues

**Patterns**:

```python
ENVIRONMENT_PATTERNS = [
    r'quota.*exceeded',
    r'already exists',
    r'cluster.*unstable',
    r'pvc.*failed',
]
```

## Classification Algorithm

### Rule-Based Classification

```python
def classify_failure(failure_message, stacktrace):
    """Classify failure based on message and stacktrace."""
    text = f"{failure_message} {stacktrace}".lower()

    # Check each category in priority order
    for pattern in INFRASTRUCTURE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return 'infrastructure'

    for pattern in DEPENDENCY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return 'dependency'

    for pattern in CONFIGURATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return 'configuration'

    for pattern in REGRESSION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return 'regression'

    for pattern in FLAKE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return 'flake'

    for pattern in ENVIRONMENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return 'environment'

    return 'unknown'
```

### Flake Detection

```sql
-- Find tests that sometimes pass, sometimes fail
WITH test_results AS (
    SELECT
        test_suite,
        test_name,
        status,
        COUNT(*) as count
    FROM test_cases
    GROUP BY test_suite, test_name, status
)
SELECT
    tr_pass.test_suite,
    tr_pass.test_name,
    tr_pass.count as passes,
    COALESCE(tr_fail.count, 0) as failures,
    ROUND(100.0 * COALESCE(tr_fail.count, 0) / (tr_pass.count + COALESCE(tr_fail.count, 0)), 2) as flake_rate
FROM test_results tr_pass
LEFT JOIN test_results tr_fail
    ON tr_pass.test_suite = tr_fail.test_suite
    AND tr_pass.test_name = tr_fail.test_name
    AND tr_fail.status = 'failed'
WHERE tr_pass.status = 'passed'
  AND tr_fail.count > 0  -- Has both passes and failures
ORDER BY flake_rate DESC;
```

## Validation

### Manual Review

Sample random failures from each category:

```sql
-- Sample 10 infrastructure failures for validation
SELECT
    tc.test_name,
    tc.failure_message,
    tc.stacktrace
FROM test_cases tc
WHERE tc.status = 'failed'
  AND tc.failure_type = 'infrastructure'
ORDER BY RANDOM()
LIMIT 10;
```

### Accuracy Metrics

- **Precision**: Correctly classified / total in category
- **Recall**: Correctly classified / total actually in category
- **F1 Score**: Harmonic mean of precision and recall

## Unknown Category

Failures that don't match any pattern need manual review:

```sql
-- Find unclassified failures
SELECT
    test_name,
    failure_message,
    COUNT(*) as occurrences
FROM test_cases
WHERE status = 'failed'
  AND (failure_type IS NULL OR failure_type = 'unknown')
GROUP BY test_name, failure_message
ORDER BY occurrences DESC;
```

## Continuous Improvement

1. Review unknown failures
2. Add new patterns
3. Refine existing patterns
4. Validate classification accuracy
5. Update documentation

## Related

- [Overview](overview.md)
- [Failure Types](../failure-types/01-infrastructure.md) - Detailed failure category analysis
- [SQL & Python](code.md)
