# Quarantine Chronic Failures

## Priority: Tier 3 - Process & Monitoring

**Status**: 📝 Placeholder - Detailed guide to be written

**Impact**: Medium - Don't block PRs on known-flaky tests
**Effort**: Low - Test organization and policy
**Cost**: Free
**Timeline**: 1 week

## Overview

This document will provide guidance on quarantining tests with chronic high failure rates (>70%) so they don't block PR merges while still tracking their status.

## Planned Content

- [ ] Quarantine criteria (what tests qualify)
- [ ] Implementation in Prow (optional vs required)
- [ ] Separate test suite organization
- [ ] Monitoring and reporting on quarantined tests
- [ ] Process for graduating tests back to required
- [ ] Communication strategy with developers

## Quarantine Criteria

Based on [Common Failures](../findings/common-failures.md) and [Flake Rate Analysis](../findings/flake-rate.md):

### Immediate Quarantine (>80% Failure Rate)
- **TestOdhOperator**: 81.5% failure rate (4,378 failures)
- **cluster install: overall**: 91.9% failure rate
- **cluster install: other**: 92.8% failure rate

### Consider Quarantine (>70% Failure Rate)
- **TestOdhOperator/services/group_1**: 65.0% failure rate
- **TestOdhOperator/services**: 62.5% failure rate

### Criteria
1. Failure rate > 70% over last 30 days
2. At least 50 test executions in period
3. Failures are infrastructure-related (not code bugs)

## Implementation

### Prow Configuration

```yaml
# Mark as optional (informational only)
- name: pull-ci-opendatahub-operator-e2e-quarantine
  optional: true  # Don't block merge
  run_if_changed: ".*"  # Still run on all PRs
```

### Test Suite Organization

```
tests/
  e2e/              # Required tests (must pass)
  e2e-quarantine/   # Quarantined tests (informational)
```

## Benefits

- ✅ PRs can merge despite known-flaky tests
- ✅ Still track test status (not ignored)
- ✅ Reduce developer frustration
- ✅ Focus on fixing quarantined tests
- ✅ Clear signal when tests are reliable enough to graduate

## Process

### Quarantine
1. Identify test with >70% failure rate for 30 days
2. Verify failures are infrastructure (not code bugs)
3. Move to quarantine suite
4. Mark as optional in Prow
5. Create issue to fix underlying problem

### Graduate Back
1. Test achieves <30% failure rate for 30 days
2. Verify improvements are sustainable
3. Move back to required suite
4. Monitor for regression

## Monitoring

Dashboard showing:
- Current quarantined tests
- Time in quarantine
- Current failure rate
- Trend (improving/degrading)
- Graduation candidates

## References

- [Flake Rate Analysis](../findings/flake-rate.md) - Identify candidates
- [Test Improvements](../findings/test-improvements.md) - Fix strategies

## Status

This is a **Tier 3 recommendation** - implement after Tier 1-2 to unblock developers while fixing underlying issues.
