# Code Regressions

## Definition

Failures caused by bugs introduced in PR code changes.

## Characteristics

- Assertion failures
- Panic/runtime errors
- Nil pointer dereferences
- Logic errors
- Expected vs. actual mismatches

## Detection Patterns

```python
REGRESSION_PATTERNS = [
    r'Expected.*but got',
    r'panic:',
    r'nil pointer dereference',
    r'assertion failed',
    r'test.*failed',
    r'Error:.*expected',
    r'runtime error:',
]
```

## Statistics

From [Common Failures](../../findings/common-failures.md) failure type distribution analysis:

**Actual Code Regression Metrics**:

- **Total Regression Failures**: 4 failures (out of 39,117 total)
- **Percentage of All Failures**: **0.1%**
- **False Positive Rate**: 99.9% of failures are NOT code regressions

**Breakdown by Root Cause** (from build log analysis of 4,193 failed builds):

| Failure Type | Count | % of Failures |
|--------------|-------|---------------|
| **Infrastructure** | **3,673** | **87.6%** |
| Configuration | 514 | 12.3% |
| **Code Regression** | **4** | **0.1%** |
| Unknown/Other | 3 | 0.1% |

**Critical Finding**: Only 4 failures (0.1%) show clear signs of code issues (panics, nil pointers, assertion failures). This means:

1. **The CI system is failing to catch bugs** - Only 0.1% of failures are real code problems
2. **99.9% false positive rate** - Overwhelming noise drowns out the signal
3. **Developers can't trust test failures** - When tests fail, there's a 99.9% chance the code is fine

**Same-SHA Evidence** (from [Same-SHA Analysis](../../findings/same-sha-analysis.md)):

- **1,527 PR+SHA combinations** had identical code produce both pass and fail results
- **63.1% of PRs** experienced same-SHA flakes (proven not code issues)
- **Only 8-10 PRs** out of 832 likely had real code failures (closed unmerged with only failures)
- **Conservative estimate**: **~95% of failures are infrastructure/flakes, only ~5% potentially code-related**

## Example Failures

Based on detection patterns used in [Common Failures](../../findings/common-failures.md) analysis, actual code regression errors would appear as:

**Panic/Runtime Errors**:
```
panic: runtime error: invalid memory address or nil pointer dereference
[signal SIGSEGV: segmentation violation code=0x1 addr=0x0 pc=0x123456]

panic: interface conversion: interface {} is nil, not string
```

**Assertion Failures**:
```
Expected:
    <int>: 1
to equal
    <int>: 0

Assertion failed: deployment should have 1 replica, but got 0

Expected condition Available=True, got Available=False
```

**Nil Pointer Dereferences**:
```
runtime error: invalid memory address or nil pointer dereference
  attempting to access field of nil pointer

Error: cannot dereference nil deployment spec
```

**Reality**: In the actual dataset of 4,193 failed builds analyzed:
- Only **4 failures** (0.1%) matched these code regression patterns
- The remaining **4,189 failures** (99.9%) were infrastructure/configuration issues
- This is why these are "expected" examples - real code regressions are extremely rare in the data

**What Actually Causes Failures** (87.6% of all failures):
```
Error: context deadline exceeded
  Timeout waiting for pod to become ready

ErrImagePull: Failed to pull image
  Registry returned error: rate limit exceeded

Connection refused: dial tcp <ip>:<port>
  Service not listening or unavailable

Operator unavailable (null): operator is not reporting conditions
```

These infrastructure errors look like test failures but are actually environmental issues, not code bugs.

## Common Causes

### Logic Errors

```go
// Bug: Off-by-one error
for i := 0; i <= len(items); i++ {  // Should be i < len(items)
    process(items[i])
}
```

### Nil Pointer Dereference

```go
// Bug: Not checking for nil
deployment := getDeployment(name)
replicas := *deployment.Spec.Replicas  // Panic if deployment is nil

// Fix: Check for nil
deployment := getDeployment(name)
if deployment != nil && deployment.Spec.Replicas != nil {
    replicas := *deployment.Spec.Replicas
}
```

### Incorrect Assumptions

```go
// Bug: Assuming pod is ready immediately
pod := createPod()
if pod.Status.Phase != corev1.PodRunning {
    return errors.New("pod not running")
}

// Fix: Wait for readiness
Eventually(func() corev1.PodPhase {
    pod := getPod()
    return pod.Status.Phase
}, timeout).Should(Equal(corev1.PodRunning))
```

## Impact

- Blocks PR merge
- Requires code fixes
- May indicate insufficient local testing
- Could mask other issues if not fixed

## Mitigation

### Development Practices

1. Run tests locally before pushing
2. Use IDE/linter for nil checks
3. Code review focus on error handling
4. Add validation in controllers

### Testing Improvements

1. Add unit tests for edge cases
2. Integration tests for common scenarios
3. Mutation testing to verify test coverage
4. Static analysis tools (golangci-lint)

## Distinguishing Factors

**Regression**: Consistently fails on specific PR, passes on main

**Flake**: Intermittent on same code

**Infrastructure**: Not correlated with code changes

## Query for Analysis

```sql
-- Regression failures by PR
SELECT
    pr.pr_number,
    pr.title,
    pr.author,
    COUNT(DISTINCT tc.id) as regression_failures
FROM pull_requests pr
JOIN test_runs tr ON pr.pr_number = tr.pr_number
JOIN test_cases tc ON tr.id = tc.test_run_id
WHERE tc.status = 'failed'
  AND tc.failure_type = 'regression'
GROUP BY pr.pr_number, pr.title, pr.author
ORDER BY regression_failures DESC
LIMIT 20;
```

## Related

- [Failure Classification](../failures/classification.md)
- [Test Framework](../../prow/test-framework.md)
