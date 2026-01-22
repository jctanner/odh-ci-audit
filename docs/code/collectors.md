# Collectors

## Overview

Data collectors for GitHub and GCS artifacts.

## GitHub Collector

```python
from ci_audit.collectors.github_collector import GitHubCollector

collector = GitHubCollector(token=github_token)

# Get PRs in date range
prs = collector.get_pull_requests(
    repo="opendatahub-io/opendatahub-operator",
    start_date=datetime(2025, 10, 1),
    end_date=datetime(2025, 12, 31)
)

# Get PR details
pr = collector.get_pull_request(repo, pr_number=1234)
```

## GCS Collector

```python
from ci_audit.collectors.gcs_collector import GCSCollector

collector = GCSCollector(bucket="test-platform-results")

# List builds for PR
builds = collector.list_builds(pr_number=1234)

# Download artifact
content = collector.download_artifact(
    path="pr-logs/pull/.../started.json"
)
```

## Artifact Parser

```python
from ci_audit.collectors.artifact_parser import ArtifactParser

parser = ArtifactParser()

# Parse JUnit XML
test_cases = parser.parse_junit(xml_content)

# Parse Prow JSON
metadata = parser.parse_prowjob(json_content)

# Extract errors from build log
errors = parser.extract_errors(log_content)
```

## Related

- [API Reference - Collectors](../api/collectors.md)
- [GCS Artifact Structure](../prow/artifacts.md)
