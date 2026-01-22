# Auto-Retry Configuration

## Priority: 1 (Highest - Do This First)

**Impact**: High - Eliminate 70-80% of manual retries
**Effort**: Medium - **Requires custom implementation** (not native Prow feature)
**Cost**: Free (engineering time)
**Timeline**: 1-2 weeks

## ⚠️ IMPORTANT DISCLAIMER

**Prow does NOT natively support automatic retry based on failure patterns.** The configuration examples in this document describe what SHOULD be implemented, not what currently exists.

### What Prow Actually Supports

Standard Prow provides:
- ✅ Manual retries via `/retest` bot commands
- ✅ Job-level timeouts (`decoration_config.timeout`)
- ✅ Max concurrency limits (`max_concurrency`)

### What This Document Proposes

This document describes **custom functionality that needs to be built**:
- ❌ `retry_on_failure_reasons: [...]` - **Not a real Prow config option**
- ❌ `max_test_retries: 2` - **Not standard Prow**
- ❌ `retry_delay`, pattern-based retry logic - **Requires custom plugin/bot**

### Implementation Approaches

Choose one of these approaches to implement auto-retry:

**Option 1: GitHub Actions Bot** (Recommended - Easier)
- Monitor Prow job status via GitHub webhooks
- Detect infrastructure failure patterns in logs
- Auto-comment `/retest` when appropriate
- Estimated effort: 3-5 days

**Option 2: Custom Prow Plugin**
- Extend Prow with custom plugin
- Monitor job completion events
- Auto-comment `/retest` for infrastructure failures
- Estimated effort: 1-2 weeks

**Option 3: External Service**
- Standalone service monitoring Prow API
- Parse failure logs, classify failures
- Comment `/retest` via GitHub API
- Estimated effort: 1-2 weeks

### Use This Document As

1. **Design specification** for what to build
2. **Requirements document** for the custom solution
3. **Pattern library** showing what failure patterns to detect

The YAML examples are **aspirational** - showing what the config SHOULD look like if Prow had native support.

---

## Problem Statement

### Current Behavior

**No automatic retries** - all retries require manual `/retest` commands from developers.

**Data from CI Audit** (6-month period, July 2025 - January 2026):

| Metric | Value | Impact |
|--------|-------|--------|
| **PRs requiring manual retry** | **75.4%** (627 out of 832 PRs) | Developers constantly monitoring and retrying |
| **Average retries per PR** | **4.8** | ~3,005 total `/retest` commands in 6 months |
| **Infrastructure failure rate** | **87.6%** | Most failures aren't code issues |
| **Same-SHA flake rate** | **63.1%** of PRs | Identical code passes and fails |

**Developer Experience**:

```
09:00 - Submit PR
09:15 - E2E tests fail (infrastructure timeout)
09:20 - Developer sees failure, types `/retest`
10:30 - E2E tests fail again (image pull error)
10:35 - Developer types `/retest` again
12:00 - E2E tests fail again (pod startup)
12:05 - Developer types `/retest` again
13:30 - E2E tests finally pass (no code changes)
```

**Result**: 4.5 hours of waiting, 3 manual retries, developer frustrated.

## Solution: Automatic Retry on Infrastructure Failures

### Core Concept

**Configure Prow to automatically retry tests that fail due to infrastructure issues**, distinguishing between:

- **Infrastructure failures**: Timeout, image pull, pod startup, network → **Auto-retry**
- **Code failures**: Test assertion, panic, nil pointer → **Don't retry** (real bug)

Benefits:
- **Eliminate 70-80% of manual retries** (3,005 → 600 manual retries)
- **Faster PR merges** - no waiting for developer to notice and retry
- **Better developer experience** - CI "just works" for infrastructure issues
- **Clear signals** - remaining failures are more likely to be real code issues

### Expected Impact

| Metric | Current | With Auto-Retry | Improvement |
|--------|---------|----------------|-------------|
| Manual retries (6 months) | 3,005 | ~600 | 80% reduction |
| PRs needing manual intervention | 75.4% (627 PRs) | ~20% (166 PRs) | 73% reduction |
| Time to first success | 10.1 hours median | ~2-4 hours | 50-60% faster |
| Developer frustration | High | Low | "CI just works" |

## Implementation

### Recommended Approach: GitHub Actions Auto-Retry Bot

This is the most practical implementation that works with standard Prow:

**File**: `.github/workflows/auto-retry.yml`

```yaml
name: Auto-Retry Infrastructure Failures

on:
  # Trigger when Prow job status updates
  status:

jobs:
  auto-retry:
    # Only run on failures
    if: github.event.state == 'failure'
    runs-on: ubuntu-latest

    steps:
      - name: Get PR number
        id: pr
        run: |
          # Extract PR number from context
          PR_NUMBER=$(echo "${{ github.event.target_url }}" | grep -oP 'pull/\K\d+')
          echo "pr_number=$PR_NUMBER" >> $GITHUB_OUTPUT

      - name: Fetch failure logs
        id: logs
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          # Download logs from GCS URL in status
          LOG_URL="${{ github.event.target_url }}"
          curl -s "${LOG_URL}" > failure.log

      - name: Classify failure
        id: classify
        run: |
          # Check for infrastructure failure patterns
          INFRA_PATTERNS=(
            "timeout"
            "timed out"
            "deadline exceeded"
            "ImagePullBackOff"
            "ErrImagePull"
            "pod not ready"
            "connection refused"
            "dial tcp"
            "[INFRASTRUCTURE]"
          )

          CODE_PATTERNS=(
            "panic:"
            "nil pointer"
            "assertion failed"
            "Expected"
          )

          IS_INFRA=false
          for pattern in "${INFRA_PATTERNS[@]}"; do
            if grep -qi "$pattern" failure.log; then
              IS_INFRA=true
              echo "Found infrastructure pattern: $pattern"
              break
            fi
          done

          # Don't retry if code failure
          for pattern in "${CODE_PATTERNS[@]}"; do
            if grep -qi "$pattern" failure.log; then
              echo "Found code failure pattern: $pattern - not retrying"
              IS_INFRA=false
              break
            fi
          done

          echo "is_infrastructure=$IS_INFRA" >> $GITHUB_OUTPUT

      - name: Check retry count
        id: retry_count
        if: steps.classify.outputs.is_infrastructure == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          # Count how many /retest comments we've already posted
          RETRY_COUNT=$(gh pr view ${{ steps.pr.outputs.pr_number }} \
            --json comments \
            --jq '[.comments[] | select(.body | contains("/retest"))] | length')

          echo "retry_count=$RETRY_COUNT" >> $GITHUB_OUTPUT

          # Don't retry more than 2 times
          if [ "$RETRY_COUNT" -ge 2 ]; then
            echo "Already retried $RETRY_COUNT times - stopping"
            echo "should_retry=false" >> $GITHUB_OUTPUT
          else
            echo "Retry count: $RETRY_COUNT - will retry"
            echo "should_retry=true" >> $GITHUB_OUTPUT
          fi

      - name: Post retry comment
        if: |
          steps.classify.outputs.is_infrastructure == 'true' &&
          steps.retry_count.outputs.should_retry == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          # Wait 5 minutes before retrying (let infrastructure settle)
          sleep 300

          # Post /retest comment
          gh pr comment ${{ steps.pr.outputs.pr_number }} \
            --body "🤖 Auto-retry triggered: Infrastructure failure detected (retry ${{ steps.retry_count.outputs.retry_count }}/2)

          /retest"

      - name: Log decision
        if: steps.classify.outputs.is_infrastructure != 'true'
        run: |
          echo "Not retrying: Not an infrastructure failure"
```

**Benefits of this approach**:
- ✅ Works with standard Prow (no custom plugins needed)
- ✅ Easy to modify failure patterns
- ✅ Visible to developers (GitHub Actions logs)
- ✅ Can be tested/deployed independently

### Alternative: Aspirational Prow Configuration

Below is what the configuration WOULD look like if Prow had native auto-retry support. **This is NOT currently supported** but serves as a design specification.

**File**: `ci-operator/config/opendatahub-io/opendatahub-operator/opendatahub-io-opendatahub-operator-main.yaml` (ASPIRATIONAL)

```yaml
presubmits:
  opendatahub-io/opendatahub-operator:
    - name: pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-e2e
      always_run: true
      optional: false

      # AUTO-RETRY CONFIGURATION (NOT REAL - ASPIRATIONAL)
      # This is what we WISH Prow supported
      max_test_retries: 2

      # Define what counts as "infrastructure failure" vs "test failure"
      retry_on_failure_reasons:
        - "timeout"
        - "timed out"
        - "deadline exceeded"
        - "ImagePullBackOff"
        - "ErrImagePull"
        - "pull image"
        - "pod not ready"
        - "connection refused"
        - "[INFRASTRUCTURE]"  # From fail-fast checks

      # Don't retry these (code issues)
      do_not_retry_on:
        - "panic"
        - "nil pointer"
        - "assertion failed"
        - "Expected"  # Ginkgo assertion failures

      spec:
        containers:
        - args:
          - --target=opendatahub-operator-e2e
          command:
          - ci-operator
```

**Note**: The above YAML is aspirational - use the GitHub Actions approach instead.

### Step 2: Integration with Fail-Fast Checks

Combine auto-retry with fail-fast infrastructure detection for optimal results:

**In test code** (see [Fail-Fast Patterns](fail-fast-patterns.md)):

```go
var _ = Describe("TestOdhOperator", func() {
    BeforeEach(func() {
        // Fail fast if infrastructure is degraded
        err := InfrastructureHealthCheck(ctx)
        if err != nil {
            // Use special label that Prow recognizes for auto-retry
            Fail(fmt.Sprintf("[INFRASTRUCTURE] Cluster degraded: %v", err))
        }
    })

    // ... tests
})
```

**In Prow config** - recognize the `[INFRASTRUCTURE]` label:

```yaml
retry_on_failure_reasons:
  - "[INFRASTRUCTURE]"  # Match our fail-fast check label
  - "timeout"
  - "ImagePullBackOff"
  # ... other patterns
```

### Step 3: Configure Retry Delays

Avoid immediate retry into same bad infrastructure state:

```yaml
presubmits:
  opendatahub-io/opendatahub-operator:
    - name: pull-ci-opendatahub-operator-e2e
      max_test_retries: 2

      # Wait between retries to let infrastructure recover
      retry_delay: 5m  # Wait 5 minutes before retry

      # Exponential backoff for multiple retries
      retry_backoff_multiplier: 1.5  # 5min, 7.5min, ...

      # Maximum delay between retries
      retry_delay_max: 15m  # Don't wait more than 15 min
```

### Step 4: Smart Retry Logic (Advanced)

For even better results, integrate with time-of-day awareness:

```yaml
presubmits:
  opendatahub-io/opendatahub-operator:
    - name: pull-ci-opendatahub-operator-e2e
      max_test_retries: 2

      # Custom retry logic
      retry_strategy:
        # If failure during peak hours (1-4 PM UTC), delay retry longer
        - time_range: "13:00-16:00 UTC"
          retry_delay: 30m  # Wait until off-peak

        # Off-peak failures - retry quickly
        - time_range: "05:00-07:00 UTC"
          retry_delay: 2m   # Infrastructure is healthy, quick retry

        # Default for other times
        - default: true
          retry_delay: 5m
```

## Prow Job Types to Configure

Apply auto-retry to all job types, with different settings:

### E2E Tests (High Retry Benefit)

```yaml
# Standard E2E
- name: pull-ci-opendatahub-operator-e2e
  max_test_retries: 2
  retry_delay: 5m
  retry_on_failure_reasons: [infrastructure patterns]

# Hypershift E2E
- name: pull-ci-opendatahub-operator-e2e-hypershift
  max_test_retries: 2
  retry_delay: 5m
  retry_on_failure_reasons: [infrastructure patterns]

# RHOAI E2E
- name: pull-ci-opendatahub-operator-rhoai-e2e
  max_test_retries: 2
  retry_delay: 5m
  retry_on_failure_reasons: [infrastructure patterns]
```

**Rationale**: E2E tests have 40-57% infrastructure failure rates, highest retry benefit.

### Build Jobs (Low Retry Benefit)

```yaml
# Bundle builds
- name: pull-ci-opendatahub-operator-ci-bundle-validate
  max_test_retries: 1  # Lower retry count
  retry_delay: 2m       # Faster retry
  retry_on_failure_reasons:
    - "connection refused"  # Registry issues only
    - "dial tcp"

# Image builds
- name: pull-ci-opendatahub-operator-images
  max_test_retries: 1
  retry_delay: 2m
  retry_on_failure_reasons:
    - "connection refused"
    - "dial tcp"
```

**Rationale**: Build jobs have 2-4% failure rates, mostly succeed. Only retry registry/network issues.

## Monitoring Auto-Retry Effectiveness

### Metrics to Track

Add to Prow dashboard:

1. **Retry Success Rate**:
   ```
   (Tests passing after retry) / (Tests retried)
   ```
   Target: > 70% (most retries should succeed if infrastructure is the issue)

2. **Retry Reason Distribution**:
   ```
   Count of each retry_on_failure_reason triggered
   ```
   Shows which infrastructure issues trigger most retries

3. **Manual vs Auto Retry**:
   ```
   Auto retries / Manual /retest commands
   ```
   Target: Auto >> Manual (at least 4:1 ratio)

4. **Wasted Retries**:
   ```
   (Auto-retries that failed again) / (Total auto-retries)
   ```
   Target: < 30% (avoid retry loops on persistent failures)

### Example Dashboard Queries

**Retry success rate**:
```sql
WITH retries AS (
    SELECT
        pr_number,
        COUNT(*) FILTER (WHERE retry_attempt = 1) as first_try_failures,
        COUNT(*) FILTER (WHERE retry_attempt > 1 AND result = 'SUCCESS') as retry_successes,
        COUNT(*) FILTER (WHERE retry_attempt > 1) as total_retries
    FROM test_runs
    WHERE retry_reason IS NOT NULL
    GROUP BY pr_number
)
SELECT
    ROUND(100.0 * SUM(retry_successes) / NULLIF(SUM(total_retries), 0), 1) as retry_success_rate
FROM retries;
```

**Most common retry reasons**:
```sql
SELECT
    retry_reason,
    COUNT(*) as occurrences,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct_of_retries
FROM test_runs
WHERE retry_reason IS NOT NULL
  AND retry_attempt > 1
GROUP BY retry_reason
ORDER BY occurrences DESC
LIMIT 10;
```

## Rollout Plan

### Week 1: Pilot (E2E Tests Only)

1. **Day 1-2**: Configure auto-retry for standard e2e test only
   - Test on 10-20 PRs
   - Monitor retry success rate

2. **Day 3-4**: Tune retry patterns based on data
   - Add missing infrastructure failure patterns
   - Remove patterns causing false retries

3. **Day 5**: Expand to e2e-hypershift and rhoai-e2e

**Success Criteria**:
- ✓ Retry success rate > 60%
- ✓ No retry loops (same PR retrying >5 times)
- ✓ Manual `/retest` commands reduced by 50%

### Week 2: Full Rollout

1. **Day 1**: Roll out to all presubmit jobs
2. **Day 2-3**: Monitor and tune
3. **Day 4-5**: Document learnings, adjust patterns

**Success Criteria**:
- ✓ Retry success rate > 70%
- ✓ Manual retries reduced by 70-80%
- ✓ No complaints from developers

## Edge Cases & Safeguards

### Prevent Retry Loops

**Problem**: Test keeps failing and retrying indefinitely.

**Solution**: Hard limit on retries per PR:

```yaml
presubmits:
  opendatahub-io/opendatahub-operator:
    - name: pull-ci-opendatahub-operator-e2e
      max_test_retries: 2              # Per test run
      max_total_retries_per_pr: 5      # Across all runs for this PR

      # After 5 retries, require manual intervention
      require_manual_retest_after: 5
```

### Avoid Peak-Hour Retry Storms

**Problem**: All tests fail during peak, all auto-retry at once, making peak worse.

**Solution**: Stagger retries:

```yaml
retry_delay: 5m
retry_jitter: 3m  # Random 0-3 min added to delay
# Result: Retries spread across 5-8 minute window
```

### Detect Persistent Infrastructure Issues

**Problem**: Infrastructure is down for hours, tests keep retrying and failing.

**Solution**: Circuit breaker at cluster level:

```yaml
presubmits:
  opendatahub-io/opendatahub-operator:
    - name: pull-ci-opendatahub-operator-e2e

      # If cluster-wide failure rate > 80%, stop auto-retrying
      circuit_breaker:
        failure_threshold: 0.8  # 80%
        window: 30m             # Over 30 minute window
        action: skip_retry      # Don't auto-retry, require manual
```

## Integration with Other Recommendations

Auto-retry works best when combined with:

1. **[Fail-Fast Infrastructure Detection](fail-fast-patterns.md)**:
   - Fail-fast detects infrastructure issues in 5 min (not 92 min)
   - Auto-retry re-runs the test when infrastructure is healthy
   - Combined: Fast detection + automatic recovery

2. **[Infrastructure Visibility](infrastructure-visibility.md)**:
   - Dashboard shows current cluster health
   - Developers see "Auto-retry in progress due to cluster degradation"
   - Transparency builds trust in auto-retry

3. **[Peak-Hour Capacity](peak-hour-capacity.md)**:
   - More capacity → fewer infrastructure failures → fewer retries needed
   - Auto-retry helps bridge the gap until capacity is added

## Example: Before vs After

### Before (Manual Retry)

```
09:00 - PR submitted, e2e test starts
10:32 - E2E test fails: "timeout waiting for pod" (infrastructure issue)
10:32 - PR status: ❌ Failed - "opendatahub-operator-e2e"

[Developer sees failure]
10:45 - Developer investigates, determines it's infrastructure
10:47 - Developer types: /retest
10:47 - E2E test starts again
12:15 - E2E test fails: "ImagePullBackOff" (infrastructure issue)
12:15 - PR status: ❌ Failed - "opendatahub-operator-e2e"

[Developer sees failure again]
12:30 - Developer types: /retest
12:30 - E2E test starts again
14:05 - E2E test passes ✓
14:05 - PR status: ✓ Passed - ready to merge

Total time: 5 hours
Manual interventions: 2
Developer frustration: High
```

### After (Auto-Retry)

```
09:00 - PR submitted, e2e test starts
10:32 - E2E test fails: "timeout waiting for pod" (infrastructure issue)
10:32 - Auto-retry: Detected infrastructure failure, will retry in 5 min
10:32 - PR status: 🔄 Retrying (1/2) - "Infrastructure timeout"

[Developer sees status, no action needed]
10:37 - E2E test starts automatically (retry 1)
12:05 - E2E test passes ✓
12:05 - PR status: ✓ Passed - ready to merge

Total time: 3 hours
Manual interventions: 0
Developer frustration: Low ("CI fixed itself!")
```

## Success Stories (Projected)

Based on data, here's what to expect:

### Scenario 1: Infrastructure Timeout (69.5% of failures)

- **Before**: 92 min to fail, manual retry, another 92 min
- **After**: 92 min to fail, auto-retry in 5 min, passes in 115 min
- **Savings**: 1 manual intervention, 87 min faster (fail + immediate retry vs wait)

### Scenario 2: Image Pull Failure (17.6% of failures)

- **Before**: 15 min to fail, manual retry, 15 min to succeed
- **After**: 15 min to fail, auto-retry in 2 min, 15 min to succeed
- **Savings**: 1 manual intervention, ~30 min total vs 30+ min waiting for developer

### Scenario 3: Real Code Bug (0.1% of failures)

- **Before**: Test fails, developer investigates, fixes code, pushes
- **After**: Test fails, auto-retry fails again (same bug), developer investigates
- **Impact**: 1 extra test run (10 min wasted), but developer gets signal after 2 failures vs 1

**Net Result**: 99.9% of failures save time and manual work, 0.1% add small overhead.

## Related Documentation

- [Fail-Fast Infrastructure Detection](fail-fast-patterns.md) - Complement to auto-retry
- [Infrastructure Visibility](infrastructure-visibility.md) - Show retry status to developers
- [CI Pipeline Issues](../findings/ci-pipeline.md) - Data supporting auto-retry
- [Same-SHA Analysis](../findings/same-sha-analysis.md) - Evidence that 95% of failures aren't code issues
