# Job Types & Workflows

## Overview

Each PR triggers multiple Prow job types for comprehensive testing.

## Common Job Types

### E2E Tests

**Standard E2E**: `pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-e2e`

- Full e2e test suite on standard OpenShift cluster
- Tests all operator components
- Longest running job (~30-60 minutes)

**RHOAI E2E**: `pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-rhoai-e2e`

- Red Hat OpenShift AI specific tests
- Additional RHOAI components and configurations
- Similar duration to standard e2e

**Hypershift E2E**: `pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-e2e-hypershift`

- Tests on Hypershift (hosted control planes)
- Different cluster topology
- May have different failure modes

### Build Jobs

**Bundle Build**: `pull-ci-opendatahub-io-opendatahub-operator-main-ci-bundle-*`

- Validates operator bundle format
- Checks CSV, CRDs, manifests
- Fast (~5-10 minutes)

**Image Build**: `pull-ci-opendatahub-io-opendatahub-operator-main-images`

- Builds operator container image
- Fast (~5-10 minutes)

**Image Mirror**: `pull-ci-opendatahub-io-opendatahub-operator-main-pr-image-mirror`

- Mirrors built images to test registry
- Fast (~2-5 minutes)

## Job Discovery

The audit system automatically discovers all job types per PR:

```python
# GCS path structure
base_path = f"pr-logs/pull/opendatahub-io_opendatahub-operator/{pr_number}/"

# List all job types
job_dirs = list_gcs_directories(base_path)
# Result: ['pull-ci-...-e2e/', 'pull-ci-...-rhoai-e2e/', ...]

# For each job type, list build IDs
for job_dir in job_dirs:
    build_ids = list_gcs_directories(f"{base_path}{job_dir}")
```

## Job Triggers

### Automatic

Jobs triggered automatically on PR events:

- PR opened
- New commits pushed
- PR synchronized

### Manual

Developer-triggered via bot commands:

```
/retest                    # Rerun all failed tests
/test <job-name>           # Run specific job
/test opendatahub-operator-e2e
```

### Periodic

Not part of this analysis (runs on schedule, not per-PR).

## Job Configuration

Jobs configured in `openshift/release` repository:

```yaml
# ci-operator/config/opendatahub-io/opendatahub-operator/
tests:
- as: opendatahub-operator-e2e
  steps:
    cluster_profile: aws
    test:
    - as: e2e-test
      commands: make test-e2e
      from: src
```

## Job Dependencies

Some jobs depend on others:

```
images → e2e tests
bundle → bundle validation
```

If image build fails, e2e tests won't run.

## Merge Requirements

**Required for merge**:

- All required presubmits must pass
- Configured in GitHub branch protection

**Optional jobs**:

- Informational only
- Failures don't block merge

## Database Representation

All job types stored in same `test_runs` table:

```sql
SELECT job_name, COUNT(*) as runs
FROM test_runs
GROUP BY job_name
ORDER BY runs DESC;
```

**Example Output**:

```
| job_name                                  | runs |
|-------------------------------------------|------|
| pull-ci-...-opendatahub-operator-e2e      | 523  |
| pull-ci-...-opendatahub-operator-rhoai-e2e| 498  |
| pull-ci-...-ci-bundle-validate            | 512  |
| pull-ci-...-images                        | 531  |
```

## Job-Specific Failures

Different job types have different failure patterns:

**E2E Tests**:

- Infrastructure timeouts
- Test flakes
- Component deployment failures

**Bundle Jobs**:

- CSV validation errors
- Missing CRDs
- Manifest format issues

**Image Jobs**:

- Build failures
- Missing dependencies
- Registry errors

## Findings

### Job Type Failure Rate Comparison

From [Time Cost Analysis](../findings/time-cost.md), failure rates and time wasted vary dramatically by job type:

| Job Type | Total Hours | Success Hours | Failure Hours | % Time on Failures | Efficiency |
|----------|-------------|---------------|---------------|--------------------|------------|
| **e2e** | **7,529** | 2,317 | **4,319** | **57.4%** | **Very inefficient** - majority of time wasted |
| **e2e-hypershift** | 1,069 | 327 | 533 | **49.9%** | Inefficient - nearly half time wasted |
| **rhoai-e2e** | 885 | 393 | 354 | **40.0%** | Moderately inefficient |
| bundle | 961 | 841 | 25 | 2.6% | **Highly efficient** |
| image-mirror | 714 | 637 | 24 | 3.4% | **Highly efficient** |
| images | 683 | 602 | 26 | 3.8% | **Highly efficient** |

**Key Findings**:

- **E2E tests waste 57.4% of compute time** on failures (4,319 hours = 180 days)
- **Build jobs are 15-20x more efficient** than e2e jobs (2-4% failure time vs 40-57%)
- **E2E hypershift and RHOAI e2e** show similar inefficiency patterns (40-50% wasted time)
- **Bundle, images, image-mirror** jobs complete efficiently with minimal retry burden

### Job Duration Comparison

From [CI Pipeline Issues](../findings/ci-pipeline.md), duration patterns reveal timeout behavior:

| Job Type | Result | Avg Duration | Median | P90 | Max | Pattern |
|----------|--------|--------------|--------|-----|-----|---------|
| **e2e** | FAILURE | **92.0 min** | 99.1 min | 134.2 min | **300.1 min** | Hit timeout limits |
| **e2e** | SUCCESS | **115.6 min** | 114.9 min | 133.9 min | 236.4 min | Complete naturally |
| **e2e-hypershift** | FAILURE | 87.4 min | 92.4 min | 138.8 min | 224.6 min | Hit timeout limits |
| **e2e-hypershift** | SUCCESS | 103.3 min | 97.6 min | 138.5 min | 227.9 min | Complete naturally |
| **rhoai-e2e** | FAILURE | 94.8 min | 107.7 min | 145.1 min | 199.0 min | Hit timeout limits |
| **rhoai-e2e** | SUCCESS | 110.1 min | 107.9 min | 126.5 min | 159.7 min | Complete naturally |
| bundle | FAILURE | 5.4 min | 3.1 min | 12.1 min | 50.3 min | Fail fast |
| bundle | SUCCESS | 16.5 min | 14.0 min | 28.2 min | 101.3 min | Efficient |
| images | FAILURE | 7.4 min | 4.6 min | 13.0 min | 243.8 min | Fail fast |
| images | SUCCESS | 10.9 min | 9.7 min | 16.9 min | 74.6 min | Efficient |
| image-mirror | FAILURE | 5.8 min | 3.4 min | 12.0 min | 68.8 min | Fail fast |
| image-mirror | SUCCESS | 10.6 min | 9.3 min | 16.8 min | 74.8 min | Efficient |

**Key Findings**:

1. **E2E tests take 2-3x longer than expected** (115 min success vs 30-60 min expected)
2. **Anomaly: Failed e2e runs are SHORTER than successful** (92 min vs 115 min) - failures hit timeout thresholds and abort
3. **Build jobs fail fast** (5-7 min) and succeed quickly (10-16 min) - proper fail-fast behavior
4. **E2E timeout appears to be ~120-150 minutes** based on P90 clustering around 134-145 min
5. **Build jobs show expected pattern**: Failures (5-7 min) are faster than successes (10-16 min)

## Related

- [Prow Architecture](architecture.md)
- [Test Suites](test-suites.md)
- [GCS Artifacts](artifacts.md)
