---
name: ci-audit-api
description: Use this skill when analyzing test failures efficiently, checking PR test results, or needing structured test data. Provides server-side log search and failure analysis without downloading large logs.
version: 1.0.0
---

# CI Audit API - Efficient Test Analysis

Query structured test data and search logs server-side instead of downloading 1-4MB raw logs.

## When To Use This Skill

Use this skill when:
- Analyzing test failures for a PR
- Checking test results without downloading full logs
- Searching for specific error patterns
- Getting quick test summaries
- Need failure counts or pass rates

## Quick Start

### 1. Get Test Summary (Start Here!)

```bash
# Get latest build ID for PR
BUILD_ID=$(curl -s "http://localhost:5000/api/test-runs?pr_number=3048&sort_by=started_at&sort_order=desc&per_page=1" | jq -r '.test_runs[0].build_id')

# Get summary - test counts, duration, result
curl -s "http://localhost:5000/api/test-runs/${BUILD_ID}/summary" | jq '.'
```

**Returns:**
```json
{
  "result": "FAILURE",
  "total_tests": 435,
  "passed": 410,
  "failed": 25,
  "duration_seconds": 6300
}
```

### 2. Get Only Failed Tests

```bash
# Get detailed failure data (much smaller than full log)
curl -s "http://localhost:5000/api/test-runs/${BUILD_ID}/failures" | jq '.'
```

**Returns:**
```json
{
  "failed_count": 25,
  "failures": [
    {
      "test_name": "TestOdhOperator/components/kserve",
      "failure_message": "Expected resource ready but was degraded",
      "stacktrace": "...",
      "duration_seconds": 120.5
    }
  ]
}
```

**Useful queries:**
```bash
# List all failed test names
curl -s "http://localhost:5000/api/test-runs/${BUILD_ID}/failures" | jq '.failures[].test_name'

# Count by suite
curl -s "http://localhost:5000/api/test-runs/${BUILD_ID}/failures" | jq '.failures | group_by(.test_suite) | map({suite: .[0].test_suite, count: length})'
```

### 3. Server-Side Log Search

```bash
# Search build log for pattern (JSON with context)
curl -s "http://localhost:5000/api/logs/build/${BUILD_ID}/search?q=COMPREHENSIVE-DIAGNOSTICS&format=json" | jq '.'

# Search for pattern (plain text)
curl "http://localhost:5000/api/logs/build/${BUILD_ID}/search?q=timeout"

# Search with more context
curl "http://localhost:5000/api/logs/build/${BUILD_ID}/search?q=worker.*failed&context=5&format=json"

# Search e2e log instead
curl "http://localhost:5000/api/logs/e2e/${BUILD_ID}/search?q=FAIL-FAST&format=json"
```

**Parameters:**
- `q` or `pattern` - Regex to search
- `context` (default=2) - Lines around matches
- `format` (default='text') - 'json' or 'text'

## Common Analysis Patterns

### Quick Health Check

```bash
PR_NUMBER=3048

BUILD_ID=$(curl -s "http://localhost:5000/api/test-runs?pr_number=${PR_NUMBER}&sort_by=started_at&sort_order=desc&per_page=1" | jq -r '.test_runs[0].build_id')

curl -s "http://localhost:5000/api/test-runs/${BUILD_ID}/summary" | jq '{result, total_tests, passed, failed}'
```

### Categorize Failures by Suite

```bash
curl -s "http://localhost:5000/api/test-runs/${BUILD_ID}/failures" | jq '
  .failures
  | group_by(.test_suite)
  | map({
      suite: .[0].test_suite,
      count: length,
      tests: map(.test_name)
    })'
```

### Search for Specific Issues

```bash
# Check if diagnostics ran
curl -s "http://localhost:5000/api/logs/build/${BUILD_ID}/search?q=COMPREHENSIVE-DIAGNOSTICS&format=json" | jq '.match_count'

# Find timeout errors
curl -s "http://localhost:5000/api/logs/build/${BUILD_ID}/search?q=timeout&format=json" | jq '.matches[].line'

# Multiple patterns with regex
curl -s "http://localhost:5000/api/logs/build/${BUILD_ID}/search?q=worker.*failed|node.*not.*ready&format=json"
```

### Analyze Multiple PRs

```bash
for pr in 3048 3049 3050; do
  echo "=== PR $pr ==="
  BUILD_ID=$(curl -s "http://localhost:5000/api/test-runs?pr_number=${pr}&sort_by=started_at&sort_order=desc&per_page=1" | jq -r '.test_runs[0].build_id')
  curl -s "http://localhost:5000/api/test-runs/${BUILD_ID}/summary" | jq '{pr: .pr_number, result, failed}'
done
```

## Best Practices

**DO:**
- ✓ Start with `/summary` to check for failures
- ✓ Use `/failures` instead of downloading full logs
- ✓ Search server-side for patterns
- ✓ Request JSON when you need structured data

**DON'T:**
- ✗ Download entire logs unless necessary
- ✗ Parse logs locally if you can search server-side
- ✗ Skip the summary check

## Efficiency Comparison

**Old (Inefficient):**
```bash
# Download 8,664 lines × multiple searches
curl http://localhost:5000/api/logs/build/BUILD_ID > log.txt
grep "timeout" log.txt
grep "FAIL" log.txt
```

**New (Efficient):**
```bash
# Get summary (1 small JSON)
curl http://localhost:5000/api/test-runs/BUILD_ID/summary

# Get failures only
curl http://localhost:5000/api/test-runs/BUILD_ID/failures

# Search server-side (only matches returned)
curl "http://localhost:5000/api/logs/build/BUILD_ID/search?q=timeout|FAIL&format=json"
```

**Bandwidth savings: 90%+**

## Other Useful Endpoints

```bash
# Get all test runs for PR
curl "http://localhost:5000/api/test-runs?pr_number=3048"

# Get all test cases (not just failures)
curl "http://localhost:5000/api/test-runs/${BUILD_ID}/test-cases"

# Filter test cases by status
curl "http://localhost:5000/api/test-runs/${BUILD_ID}/test-cases?status=failed"

# Get raw logs (only if needed)
curl "http://localhost:5000/api/logs/build/${BUILD_ID}"
curl "http://localhost:5000/api/logs/e2e/${BUILD_ID}"
```

## Example Script: Generate Failure Report

```bash
#!/bin/bash
PR_NUMBER=${1:-3048}

BUILD_ID=$(curl -s "http://localhost:5000/api/test-runs?pr_number=${PR_NUMBER}&sort_by=started_at&sort_order=desc&per_page=1" | jq -r '.test_runs[0].build_id')

echo "=== Test Summary for PR $PR_NUMBER ==="
curl -s "http://localhost:5000/api/test-runs/${BUILD_ID}/summary" | jq '{result, total: .total_tests, passed, failed, duration_seconds}'

echo -e "\n=== Failed Tests ==="
curl -s "http://localhost:5000/api/test-runs/${BUILD_ID}/failures" | jq -r '.failures[] | "- \(.test_suite)/\(.test_name): \(.failure_message // "No message")"'

echo -e "\n=== Infrastructure Failures ==="
curl -s "http://localhost:5000/api/logs/build/${BUILD_ID}/search?q=worker.*failed|timeout.*cluster&format=json" | jq '.match_count'
```

## When To Download Full Logs

Only download full logs when:
- Need complete context
- Searching for unexpected/unknown patterns
- Debugging parser issues
- Creating comprehensive reports

For 90% of cases, structured endpoints are faster.
