---
name: fetch-e2e-logs
description: This skill should be used when the user asks to "fetch e2e logs", "download test logs", "get the latest log", "pull PR test results", or needs to retrieve e2e test logs from ci_audit without full analysis.
version: 1.0.0
---

# Fetch E2E Test Logs

Quick retrieval of the latest e2e test logs for a PR from the ci_audit REST API.

## When To Use This Skill

Use this skill when:
- User wants just the logs without analysis
- Need raw log data for manual inspection
- Want to grep/search logs directly
- Preparing for manual debugging

## How To Fetch Logs

### Get Latest Build ID

```bash
BUILD_ID=$(curl -s "http://localhost:5000/api/test-runs?pr_number=3048&sort_by=started_at&sort_order=desc&per_page=1" | jq -r '.test_runs[0].build_id')

if [ -z "$BUILD_ID" ] || [ "$BUILD_ID" = "null" ]; then
  echo "ERROR: No test runs found for PR 3048"
  exit 1
fi

echo "Latest build ID: $BUILD_ID"
```

### Download E2E Log

```bash
# Try e2e log first
curl -s "http://localhost:5000/api/logs/e2e/${BUILD_ID}" > /tmp/pr3048_latest.log

# Check if successful
if grep -q '"error"' /tmp/pr3048_latest.log 2>/dev/null; then
  echo "E2E log not available, trying build log..."
  curl -s "http://localhost:5000/api/logs/build/${BUILD_ID}" > /tmp/pr3048_latest.log
fi

# Verify
LINE_COUNT=$(wc -l < /tmp/pr3048_latest.log)
echo "Downloaded $LINE_COUNT lines to /tmp/pr3048_latest.log"
```

### Quick Stats

```bash
echo "=== Quick Stats ==="
echo "Total FAIL: $(grep -c '^FAIL' /tmp/pr3048_latest.log || echo 0)"
echo "Total PASS: $(grep -c '^PASS' /tmp/pr3048_latest.log || echo 0)"
echo "Failing tests: $(grep -cE '^\s+--- FAIL:' /tmp/pr3048_latest.log || echo 0)"
```

## Log Location

After fetching, the log is available at: `/tmp/pr3048_latest.log`

## Common Manual Inspection Commands

```bash
# Find all failures
grep "FAIL" /tmp/pr3048_latest.log

# Find timeouts
grep "Timed out" /tmp/pr3048_latest.log

# Find panics/crashes
grep "panic" /tmp/pr3048_latest.log

# Find specific test
grep "modelsasservice" /tmp/pr3048_latest.log

# Check API health
grep "\[API-HEALTH\]" /tmp/pr3048_latest.log
```

## Next Steps

After fetching logs:
- Use `analyze-e2e` skill for comprehensive analysis
- Manually grep for specific patterns
- Compare with previous runs
