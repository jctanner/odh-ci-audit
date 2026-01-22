# Infrastructure Failures

## Definition

Failures caused by cluster/platform infrastructure issues, not code bugs.

## Common Patterns

- Timeout waiting for pods/resources
- Image pull errors
- Network connectivity issues
- Node resource exhaustion
- Pod scheduling failures
- Storage provisioning timeouts

## Detection Patterns

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
    r'pod.*not.*ready',
    r'failed to schedule',
]
```

## Statistics

From [Infrastructure Issues](../../findings/infrastructure.md) analysis of 4,193 failed builds:

**Overall Infrastructure Failure Metrics**:

| Issue Type | Affected Builds | Affected PRs | % of Failures |
|------------|-----------------|--------------|---------------|
| **Timeouts** | **2,915** | 499 | **69.5%** |
| **Pod Startup Issues** | **2,150** | 413 | **51.3%** |
| **Image Pull Failures** | 737 | 163 | **17.6%** |
| **Network Issues** | 469 | 172 | **11.2%** |

**Note**: Categories overlap - a single build can have multiple infrastructure issues.

**Percentage of all failures**: Based on [Common Failures](../../findings/common-failures.md) analysis, **87.6% of all failures** show infrastructure error patterns in build logs.

**Trend over time**: Analysis of 6-month period (July 2025 - January 2026) shows:
- Timeout rate variability: 56.5% - 86.7% across weeks
- **No clear improvement trend**: Issues persist throughout entire period
- Image pull spikes: Some weeks show 45-58 image pull failures
- Conclusion: **Systemic and persistent**, not temporary issues

## Example Failures

**Real examples from build log analysis**:

**Timeout Errors** (69.5% of failures):
```
Error: context deadline exceeded
  Timeout waiting for pod to become ready

Timed out waiting for operator condition
  Expected: Available=True
  Actual: Available=Unknown after 5m0s

Operation timeout
  Failed to complete operation within allocated time
```

**Pod Startup Issues** (51.3% of failures):
```
Operator unavailable (null): operator is not reporting conditions
  (330 occurrences across 34 different tests)

Pod not ready: containers not initialized
  Waiting for pod "opendatahub-operator-xyz" to be ready

ContainerCreating: pod stuck in creation state
  Image pull in progress or failed
```

**Image Pull Failures** (17.6% of failures):
```
ErrImagePull: Failed to pull image
  Registry returned error: rate limit exceeded

ImagePullBackOff: Back-off pulling image
  Cannot pull image after multiple retries

Failed to pull image "quay.io/opendatahub/component:latest"
  Network timeout connecting to registry
```

**Network Issues** (11.2% of failures):
```
Connection refused: dial tcp <ip>:<port>
  Service not listening or unavailable

Network unreachable
  Routing problems or network policy blocking traffic

DNS resolution failed
  Cannot resolve service name to IP address
```

## Root Causes

**Image Pull Failures**:

- Registry rate limiting
- Incorrect image tags
- Network issues to registry
- Authentication problems

**Resource Exhaustion**:

- Node CPU/memory limits
- Pod eviction due to resource pressure
- Storage quota exceeded

**Networking**:

- DNS resolution failures
- Service mesh connectivity
- Cluster network issues
- External network dependencies

## Impact

From [Infrastructure Issues](../../findings/infrastructure.md) and [Time Cost Analysis](../../findings/time-cost.md):

**PRs Affected**:
- **499 PRs** affected by timeout issues (57% of all PRs with failures)
- **413 PRs** affected by pod startup issues (47% of all PRs with failures)
- **163 PRs** affected by image pull failures (19% of all PRs with failures)
- **172 PRs** affected by network issues (20% of all PRs with failures)

**Build Time Wasted**:
- **Total wasted CI time**: 6,689 hours (278.7 days) on failed/aborted runs
- **Failed runs duration**: 75.7 min average (3x longer than successful runs at 26.5 min)
- **Timeout contribution**: ~4,670 hours wasted on timeout-related failures
- **Infrastructure cost**: $670-$2,000+ wasted in cloud compute costs on failures

**Developer Productivity Impact**:
- **75.4% of PRs** require manual retry commands due to infrastructure failures
- **~3,005 `/retest` commands** issued in 6-month period (manual intervention overhead)
- **529 developer hours** spent waiting on failed tests (10% of 5,287 hours failed runs)
- **$52,900 productivity loss** (at $100/hour developer cost)

**False Negatives** (Real Bugs Masked):
- From [Common Failures](../../findings/common-failures.md): Only **0.1% of failures** are actual code regressions
- **87.6% infrastructure failures** drown out the **0.1% real bugs**
- Creates "cry wolf" situation where developers can't trust test failures
- From [Same-SHA Analysis](../../findings/same-sha-analysis.md): **95% of failures** aren't code issues

## Mitigation Strategies

**Short-term**:

1. Retry mechanism for transient failures
2. Increase timeouts for slow operations
3. Pre-pull commonly used images
4. Monitor cluster health

**Long-term**:

1. Improve cluster capacity planning
2. Use local image registry/mirror
3. Implement better resource limits
4. Add infrastructure health checks

## Distinguishing from Code Issues

**Infrastructure**: Affects multiple unrelated tests, not correlated with code changes

**Code Bug**: Consistent failure on specific test, correlated with PR changes

## Query for Analysis

```sql
-- Infrastructure failures by type
SELECT
    LEFT(failure_message, 50) as message_pattern,
    COUNT(*) as occurrences,
    COUNT(DISTINCT test_name) as affected_tests
FROM test_cases
WHERE status = 'failed'
  AND failure_type = 'infrastructure'
GROUP BY LEFT(failure_message, 50)
ORDER BY occurrences DESC
LIMIT 20;
```

## Related

- [Failure Classification](../failures/classification.md)
- [Failure Analysis Overview](../failures/overview.md)
