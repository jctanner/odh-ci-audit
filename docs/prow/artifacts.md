# GCS Artifact Structure

## GCS Bucket Organization

```
gs://test-platform-results/
  pr-logs/
    pull/
      opendatahub-io_opendatahub-operator/
        {PR_NUMBER}/
          {JOB_NAME}/
            {BUILD_ID}/
              started.json
              finished.json
              prowjob.json
              build-log.txt
              artifacts/
                junit_01.xml
                junit_02.xml
                ...
```

## Artifact Files

### started.json

Records job start time and metadata.

```json
{
  "timestamp": 1730462400,
  "pull": "1234",
  "repos": {
    "opendatahub-io/opendatahub-operator": "main:abc123def456"
  },
  "repo-version": "abc123def456",
  "node": "ci-op-abc123-build"
}
```

**Fields**:

- `timestamp`: Unix timestamp (seconds)
- `pull`: PR number
- `repos`: Repo and commit SHA
- `repo-version`: Commit SHA

### finished.json

Records job completion and result.

```json
{
  "timestamp": 1730464200,
  "passed": false,
  "result": "FAILURE",
  "revision": "abc123def456",
  "metadata": {
    "duration": 1800
  }
}
```

**Fields**:

- `timestamp`: Unix timestamp (seconds)
- `passed`: Boolean success indicator
- `result`: "SUCCESS", "FAILURE", or "ABORTED"
- `revision`: Commit SHA
- `metadata.duration`: Duration in seconds (optional)

### prowjob.json

Full Prowjob Kubernetes object.

```json
{
  "apiVersion": "prow.k8s.io/v1",
  "kind": "ProwJob",
  "metadata": {
    "name": "abc-123",
    "labels": {
      "prow.k8s.io/job": "pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-e2e",
      "prow.k8s.io/type": "presubmit"
    }
  },
  "spec": {
    "type": "presubmit",
    "job": "pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-e2e",
    "refs": {
      "org": "opendatahub-io",
      "repo": "opendatahub-operator",
      "pulls": [{
        "number": 1234,
        "author": "username",
        "sha": "abc123def456"
      }]
    }
  },
  "status": {
    "state": "failure",
    "startTime": "2025-11-01T10:00:00Z",
    "completionTime": "2025-11-01T10:30:00Z",
    "url": "https://prow.ci.openshift.org/view/gs/..."
  }
}
```

**Key Fields**:

- `spec.job`: Job name
- `spec.refs.pulls`: PR details
- `status.state`: "success", "failure", "aborted"
- `status.startTime/completionTime`: ISO 8601 timestamps

### build-log.txt

Console output from the entire job.

**Contents**:

- Setup logs (clone repo, install deps)
- Test execution output
- ci-operator logs
- Cleanup logs

**Size**: Can be 1-10 MB for long-running jobs

**Common Error Patterns**:

```
Error: timed out waiting for pod
panic: runtime error: nil pointer dereference
FAIL: Expected pod to be running
Error creating deployment: timeout
```

### JUnit XML Files

Test results in JUnit format.

**Naming**: `junit_01.xml`, `junit_02.xml`, etc.

**Structure**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Dashboard" tests="5" failures="1" time="123.45">
  <testcase name="Should create deployment" classname="e2e.dashboard" time="12.34">
  </testcase>
  <testcase name="Should create service" classname="e2e.dashboard" time="5.67">
    <failure message="Service not found" type="assertion">
Expected:
    &lt;*errors.StatusError | 0xc000123400&gt;: service "dashboard" not found
to succeed
    </failure>
  </testcase>
</testsuite>
```

**Elements**:

- `<testsuite>`: Test suite (one per file)
- `<testcase>`: Individual test
- `<failure>`: Failure details (if failed)
- `<skipped>`: Skipped tests

## Discovering Builds

There are two approaches to discovering test builds before downloading artifacts:

### Option 1: Prow JSON API (Recommended for Recent Data)

For builds from the last 24-48 hours, use the Prow API:

```python
import requests

# Fetch recent jobs
response = requests.get(
    "https://prow.ci.openshift.org/prowjobs.js",
    params={"omit": "annotations,labels,decoration_config,pod_spec"}
)
jobs = response.json()["items"]

# Filter to opendatahub-operator
for job in jobs:
    refs = job["spec"]["refs"]
    if refs["repo"] == "opendatahub-operator":
        # GCS path provided directly in status.url
        gcs_path = job["status"]["url"].replace(
            "https://prow.ci.openshift.org/view/gs/", "gs://"
        )
        build_id = job["status"]["build_id"]
        print(f"Build {build_id}: {gcs_path}")
```

**Advantages**:
- Single API call for all recent builds
- PR metadata included (no GitHub API needed)
- Job state pre-filtered (know failures before downloading)
- Direct GCS paths provided

See [Prow JSON API](api.md) for complete documentation.

### Option 2: GCS HTTP XML API (Historical Data)

For older builds, scan GCS bucket directly:

## Accessing Artifacts

### HTTP XML API

List directory contents:

```bash
curl "https://storage.googleapis.com/test-platform-results/?prefix=pr-logs/pull/opendatahub-io_opendatahub-operator/1234/"
```

**Response** (XML):

```xml
<ListBucketResult>
  <Contents>
    <Key>pr-logs/.../started.json</Key>
    <Size>234</Size>
    <LastModified>2025-11-01T10:00:00Z</LastModified>
  </Contents>
  <Contents>
    <Key>pr-logs/.../finished.json</Key>
    ...
  </Contents>
</ListBucketResult>
```

### Direct Download

```bash
# Download specific artifact
curl -O "https://storage.googleapis.com/test-platform-results/pr-logs/.../started.json"
```

### Python Client

```python
from ci_audit.collectors.gcs_collector import GCSCollector

collector = GCSCollector(bucket="test-platform-results")

# List builds for PR
builds = collector.list_builds(pr_number=1234)

# Download artifact
content = collector.download_artifact(gcs_path="pr-logs/.../started.json")
```

## Artifact Parsing

### JSON Artifacts

```python
import json

with open("started.json") as f:
    data = json.load(f)
    timestamp = data["timestamp"]
    pr_number = data["pull"]
```

### JUnit XML

```python
import xml.etree.ElementTree as ET

tree = ET.parse("junit_01.xml")
root = tree.getroot()

for testcase in root.findall(".//testcase"):
    name = testcase.get("name")
    status = "passed" if testcase.find("failure") is None else "failed"
```

### Build Logs

```python
with open("build-log.txt") as f:
    for line in f:
        if "Error:" in line or "FAIL:" in line:
            # Extract error
            print(line)
```

## Artifact Storage

Artifacts stored in database:

```python
# test_runs table
test_run = TestRun(
    build_id=build_id,
    pr_number=pr_number,
    result=finished["result"],
    started_at=datetime.fromtimestamp(started["timestamp"]),
    gcs_path=gcs_path,
    prowjob_metadata=prowjob  # Full JSON
)

# test_cases table (from JUnit)
test_case = TestCase(
    test_run_id=test_run.id,
    test_name=testcase.get("name"),
    status="failed" if failure else "passed",
    failure_message=failure.get("message")
)

# build_logs table
build_log = BuildLog(
    test_run_id=test_run.id,
    log_content=log_text,
    error_lines=extracted_errors  # JSON array
)
```

## Findings

### Artifact Collection Coverage

From [CI Pipeline Issues](../findings/ci-pipeline.md), analysis of artifact availability across 20,679 test runs:

| Artifact Type | Coverage | Missing | Notes |
|---------------|----------|---------|-------|
| **Build logs** | **100.0%** | 0 runs | Complete coverage across all jobs |
| **Test cases (e2e jobs)** | **99.8%** | 10 runs | Nearly complete junit XML coverage |
| **Test cases (all jobs)** | **99.9%** | 17 runs | Excellent overall coverage |

**Test case coverage by job type**:

| Job Type | Total Runs | With Test Cases | Coverage |
|----------|------------|-----------------|----------|
| e2e-hypershift | 934 | 934 | 100.0% |
| rhoai-e2e | 715 | 715 | 100.0% |
| image-mirror | 4,509 | 4,508 | 100.0% |
| bundle | 4,183 | 4,182 | 100.0% |
| images | 4,158 | 4,153 | 99.9% |
| **e2e** | 5,485 | 5,475 | **99.8%** |

**Key Findings**:

1. **Excellent artifact collection**: 99.9%+ coverage across all artifact types
2. **No systematic collection failures**: Missing artifacts are rare edge cases (17 out of 20,679 runs)
3. **Reliable junit XML parsing**: Ginkgo/Gomega test output consistently captured
4. **Complete log collection**: 100% of runs have build logs available for analysis

### Common Parsing Issues

Despite 99.9% coverage, there are 17 runs missing test case data:

**Minor Issues Identified**:

- **Cause**: Jobs likely aborted before junit XML files could be written
- **Impact**: Minimal - represents 0.08% of total runs (17 out of 20,679)
- **Distribution**: Most missing from e2e jobs (10 out of 5,485 = 0.18%)
- **Pattern**: No systematic parsing errors - isolated cases of incomplete artifact generation

**Success Indicators**:

- **100% build log parsing**: All log files successfully downloaded and parsed
- **JSON parsing**: No errors parsing `started.json`, `finished.json`, or `prowjob.json` files
- **XML parsing**: JUnit XML format is consistent and parseable across all jobs
- **No schema mismatches**: Artifact structure is stable and well-documented

**Recommendation**: Artifact collection is NOT a problem area. The CI system reliably captures test results and logs. Focus should be on the actual test reliability issues (87.6% infrastructure failures), not artifact collection.

## Related

- [Prow JSON API](api.md) - Efficient build discovery for recent data
- [Prow Architecture](architecture.md)
- [Database Schema](../setup/database-schema.md)
- [Data Collection](../setup/architecture.md)
