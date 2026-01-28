---
name: compare-e2e-runs
description: This skill should be used when the user asks to "compare test runs", "track test progress", "show improvement", "compare recent runs", "is it getting better", or wants to analyze trends across multiple e2e test executions.
version: 1.0.0
---

# Compare E2E Test Runs

Track progress by comparing multiple recent test runs to identify trends and measure improvement.

## When To Use This Skill

Use this skill when:
- User wants to see if failures are decreasing
- Need to track improvement after applying fixes
- Want to identify persistent vs intermittent failures
- Comparing test results before/after changes

## How To Compare Runs

### Fetch Recent Test Runs

```bash
# Get last 5 runs (adjust limit as needed)
curl -s "http://localhost:5000/api/test-runs?pr_number=3048&sort_by=started_at&sort_order=desc&per_page=5" > /tmp/pr3048_runs.json

# Display summary table
echo "Build ID                | Result  | Started At          | Duration"
echo "------------------------|---------|---------------------|----------"
jq -r '.test_runs[] | "\(.build_id) | \(.result) | \(.started_at) | \(.duration)s"' /tmp/pr3048_runs.json
```

### Download Logs For Each Run

```bash
jq -r '.test_runs[] | .build_id' /tmp/pr3048_runs.json | while read BUILD_ID; do
  LOG_FILE="/tmp/pr3048_${BUILD_ID}_e2e.log"

  # Try e2e log, fall back to build log
  curl -s "http://localhost:5000/api/logs/e2e/${BUILD_ID}" > "$LOG_FILE"
  if grep -q '"error"' "$LOG_FILE" 2>/dev/null; then
    curl -s "http://localhost:5000/api/logs/build/${BUILD_ID}" > "$LOG_FILE"
  fi

  echo "Downloaded $BUILD_ID: $(wc -l < "$LOG_FILE") lines"
done
```

### Compare Failure Patterns

```bash
echo "=== Failure Comparison ==="
echo "Build ID                | Total | modelsasservice | monitoring | Other"
echo "------------------------|-------|-----------------|------------|-------"

jq -r '.test_runs[] | .build_id' /tmp/pr3048_runs.json | while read BUILD_ID; do
  LOG_FILE="/tmp/pr3048_${BUILD_ID}_e2e.log"

  if [ -f "$LOG_FILE" ]; then
    TOTAL=$(grep -cE '^\s*--- FAIL:' "$LOG_FILE" 2>/dev/null || echo 0)
    MAAS=$(grep -c "FAIL.*modelsasservice" "$LOG_FILE" 2>/dev/null || echo 0)
    MON=$(grep -c "FAIL.*monitoring" "$LOG_FILE" 2>/dev/null || echo 0)
    OTHER=$((TOTAL - MAAS - MON))

    printf "%-24s| %-5d | %-15d | %-10d | %d\n" "$BUILD_ID" "$TOTAL" "$MAAS" "$MON" "$OTHER"
  fi
done
```

### Track Our Specific Fixes

```bash
echo "=== Key Test Status Tracking ==="

jq -r '.test_runs[] | .build_id' /tmp/pr3048_runs.json | while read BUILD_ID; do
  LOG_FILE="/tmp/pr3048_${BUILD_ID}_e2e.log"

  echo ""
  echo "Build: $BUILD_ID"
  echo "---"

  # Check modelsasservice deletion recovery (our fix)
  if grep -q "PASS.*modelsasservice.*deletion_recovery" "$LOG_FILE" 2>/dev/null; then
    echo "  ✓ modelsasservice deletion recovery: PASS"
  elif grep -q "FAIL.*modelsasservice.*deletion_recovery" "$LOG_FILE" 2>/dev/null; then
    echo "  ✗ modelsasservice deletion recovery: FAIL"
  fi

  # Check monitoring tests (our fix)
  if grep -q "PASS.*monitoring.*Prometheus" "$LOG_FILE" 2>/dev/null; then
    echo "  ✓ Prometheus monitoring: PASS"
  elif grep -q "FAIL.*monitoring.*Prometheus" "$LOG_FILE" 2>/dev/null; then
    echo "  ✗ Prometheus monitoring: FAIL"
  fi

  # Check if parent enabling is working
  if grep -q "Waiting for parent component.*to become ready" "$LOG_FILE" 2>/dev/null; then
    echo "  ✓ Parent readiness wait: WORKING"
  fi
done
```

### Calculate Trends

```bash
echo "=== Trend Analysis ==="

# Pass rate
RUNS=$(jq '.test_runs | length' /tmp/pr3048_runs.json)
SUCCESSES=$(jq '[.test_runs[] | select(.result == "SUCCESS")] | length' /tmp/pr3048_runs.json)
PASS_RATE=$((SUCCESSES * 100 / RUNS))

echo "Overall pass rate: $PASS_RATE% ($SUCCESSES/$RUNS runs)"

# First vs last comparison
FIRST_BUILD=$(jq -r '.test_runs[-1].build_id' /tmp/pr3048_runs.json)
LAST_BUILD=$(jq -r '.test_runs[0].build_id' /tmp/pr3048_runs.json)

FIRST_FAILS=$(grep -cE '^\s*--- FAIL:' "/tmp/pr3048_${FIRST_BUILD}_e2e.log" 2>/dev/null || echo 0)
LAST_FAILS=$(grep -cE '^\s*--- FAIL:' "/tmp/pr3048_${LAST_BUILD}_e2e.log" 2>/dev/null || echo 0)

echo ""
echo "First run: $FIRST_FAILS failures"
echo "Latest run: $LAST_FAILS failures"

if [ "$LAST_FAILS" -lt "$FIRST_FAILS" ]; then
  echo "✓ IMPROVING: $((FIRST_FAILS - LAST_FAILS)) fewer failures"
elif [ "$LAST_FAILS" -gt "$FIRST_FAILS" ]; then
  echo "✗ REGRESSING: $((LAST_FAILS - FIRST_FAILS)) more failures"
else
  echo "→ STABLE: Same number of failures"
fi
```

### Find Persistent Failures

```bash
echo "=== Persistent Failures ==="

# Tests that fail in multiple runs
cat /tmp/pr3048_*_e2e.log 2>/dev/null | \
  grep -E '^\s*--- FAIL:' | \
  sed 's/.*FAIL: //' | sed 's/ (.*//' | \
  sort | uniq -c | sort -rn | head -20

echo "^ Count = number of runs this test failed in"
```

## Interpretation

### Progress Assessment

- **Failures decreasing** → Our fixes are working ✓
- **Failures increasing** → We introduced a regression ✗
- **Stable failures** → Infrastructure or unfixed issues

### Test Patterns

- **Fails every run** → Code issue, needs fix
- **Fails sometimes** → Infrastructure timing, needs resilience or retry
- **Recently started passing** → Our fix worked ✓

### Expected After Our Fixes

Based on commits 57b346c3, d1dcd2aa, 78461703:
- modelsasservice failures should DECREASE
- Monitoring test failures should DECREASE
- Overall trend should be DOWNWARD

## Output Format

Provide:

1. **Progress Summary**
   - Are our fixes working?
   - Trend: improving/regressing/stable?

2. **Specific Test Results**
   - Which tests improved?
   - Which are still failing?

3. **Recommended Actions**
   - What to fix next
   - What's infrastructure (retry)
   - What needs investigation
