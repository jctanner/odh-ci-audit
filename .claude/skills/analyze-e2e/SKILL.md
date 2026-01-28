---
name: analyze-e2e
description: This skill should be used when the user asks to "analyze e2e", "analyze the latest test run", "check test failures", "what failed in e2e", "analyze PR test results", or discusses test failure diagnosis and root cause analysis for opendatahub-operator e2e tests.
version: 1.0.0
---

# E2E Test Failure Analysis

This skill analyzes the latest e2e test run for a PR to identify regressions, infrastructure issues, and improvement opportunities.

## When To Use This Skill

Use this skill when:
- User wants to analyze e2e test results
- A test run has completed and failures need diagnosis
- Need to distinguish infrastructure vs code issues
- Want to identify what our patches broke vs what's environmental

## How It Works

### Step 1: Fetch Latest Test Run

Query the ci_audit REST API:

```bash
# Get latest build ID
BUILD_ID=$(curl -s "http://localhost:5000/api/test-runs?pr_number=3048&sort_by=started_at&sort_order=desc&per_page=1" | jq -r '.test_runs[0].build_id')

# Get run metadata
curl -s "http://localhost:5000/api/test-runs?pr_number=3048&sort_by=started_at&sort_order=desc&per_page=1" | jq -r '.test_runs[0]'

# Download e2e log
curl -s "http://localhost:5000/api/logs/e2e/${BUILD_ID}" > /tmp/pr3048_analysis.log

# Fallback to build log if e2e not available
if grep -q '"error"' /tmp/pr3048_analysis.log 2>/dev/null; then
  curl -s "http://localhost:5000/api/logs/build/${BUILD_ID}" > /tmp/pr3048_analysis.log
fi
```

### Step 2: Quick Failure Overview

```bash
# Count failures
echo "=== Failure Summary ==="
grep -c "^\s*--- FAIL:" /tmp/pr3048_analysis.log

# List failing tests
grep -E "^\s+--- FAIL:.*\([0-9.]+s\)" /tmp/pr3048_analysis.log | sed 's/.*FAIL: //' | sort -u
```

### Step 3: Categorize Failures

#### Check Our Patches Are Working

```bash
# Subcomponent parent enabling (our fix commit 57b346c3, d1dcd2aa)
grep "Subcomponent.*detected - ensuring parent component" /tmp/pr3048_analysis.log
grep "Waiting for parent component.*to become ready" /tmp/pr3048_analysis.log

# Namespace filtering (our fix commit 78461703)
grep -A 5 "Expected resource list.*to be empty" /tmp/pr3048_analysis.log | head -20
```

#### Identify Infrastructure Issues

```bash
# API health diagnostics
grep "\[API-HEALTH\] Assessment:" /tmp/pr3048_analysis.log | tail -10

# Infrastructure timeouts
grep -E "(Timed out after|context deadline exceeded)" /tmp/pr3048_analysis.log | head -20

# Missing resources (parent component not ready yet)
grep -E "(serviceaccount|secret).*not found" /tmp/pr3048_analysis.log | head -20
```

#### Find Specific Patterns

```bash
# Deletion recovery failures
grep -B 5 "FAIL.*deletion_recovery" /tmp/pr3048_analysis.log | grep -E "(FAIL|Timed out)" | head -20

# Timeout details
grep -B 10 "Timed out after" /tmp/pr3048_analysis.log | grep -E "(RUN|FAIL)" | head -30
```

### Step 4: Classify Each Failure

For each failing test, determine:

1. **Regression (we broke it)?**
   - New failure after our commits?
   - Check git log: `git log --oneline -10`
   - Compare with known issues

2. **Infrastructure (not our fault)?**
   - API health shows HEALTHY but test failed
   - Missing ServiceAccounts/Secrets → timing issue
   - Timeouts > 300s → cluster slowness

3. **New pattern (opportunity)?**
   - First time seeing this?
   - Different error than before?
   - Chance to improve resilience?

## Analysis Output Format

Provide findings as:

### Summary
- Build ID: [id]
- Result: [SUCCESS/FAILURE]
- Pass Rate: [%]

### Regressions (What WE Broke)
- Test: [name]
- Root cause: [why]
- Fix: [what to do]

### Infrastructure Issues (Not Our Fault)
- Test: [name]
- Evidence: API-HEALTH, timeouts
- Action: Retry or add resilience

### New Discoveries
- Pattern: [what found]
- Opportunity: [how to improve]

### Next Steps
1. [Prioritized action]
2. [File/function to fix]
3. [Expected impact]

## Known Patterns (Based On Our Work)

### Tests That Should Pass Now
- **modelsasservice deletion recovery** - Fixed by parent enabling + readiness wait (commits 57b346c3, d1dcd2aa)
- **Monitoring Prometheus TLS** - Fixed by namespace filtering (commit 78461703)
- **Hypershift monitoring** - Fixed by race condition cleanup (commit 7d5aba44)

### Expected Behavior
- Subcomponent tests log: "Waiting for parent component X to become ready"
- Parent component readiness check completes before deletion recovery
- List operations filter to correct namespace

### Still Possible
- **CRD propagation delays** - Not yet fixed (Patch 18 proposed but not applied)
- **Infrastructure timeouts** - May need retry, not code fix

## Important

- **Focus on root causes, not symptoms**
- **Distinguish infrastructure from code** using API-HEALTH diagnostics
- **Be specific**: file paths, function names, line numbers
- **Prioritize regressions**: fix what we broke first
- **Don't celebrate**: just state what's broken and how to fix it
