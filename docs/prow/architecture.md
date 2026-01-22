# Prow Architecture

## What is Prow?

Prow is a Kubernetes-based CI/CD system for GitHub, developed by the Kubernetes project.

**Key Features**:

- Kubernetes-native (runs jobs as pods)
- GitHub integration (webhooks, status checks, comments)
- Artifact storage in GCS (Google Cloud Storage)
- Extensive plugin system

**Used by**: Kubernetes, OpenShift, Istio, and many other projects

## OpenShift Test Platform

The opendatahub-operator uses OpenShift's Prow instance:

- **URL**: [prow.ci.openshift.org](https://prow.ci.openshift.org)
- **GCS Bucket**: `test-platform-results`
- **Job Prefix**: `pull-ci-opendatahub-io-opendatahub-operator-*`

## Prow Workflow

```
1. Developer opens PR → GitHub webhook
2. Prow triggers jobs → Kubernetes pods
3. Tests run → Results written to GCS
4. Prow updates → GitHub status checks
5. Artifacts stored → GCS bucket (public)
```

## Job Lifecycle

### Trigger

```yaml
# Configured in ci-operator config
presubmits:
  opendatahub-io/opendatahub-operator:
  - name: pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-e2e
    always_run: true
    context: opendatahub-operator-e2e
```

### Execution

1. Prow creates Kubernetes pod
2. Pod clones repo at PR commit
3. ci-operator runs test steps
4. Results uploaded to GCS
5. Pod terminates

### Artifacts

```
gs://test-platform-results/pr-logs/pull/
  opendatahub-io_opendatahub-operator/
    {PR_NUMBER}/
      {JOB_NAME}/
        {BUILD_ID}/
          started.json
          finished.json
          prowjob.json
          artifacts/
            junit*.xml
          build-log.txt
```

## GCS Access

**Public Bucket**: No authentication required

**HTTP XML API**:

```bash
# List builds
curl https://storage.googleapis.com/test-platform-results/?prefix=pr-logs/pull/opendatahub-io_opendatahub-operator/1234/

# Download artifact
curl https://storage.googleapis.com/test-platform-results/pr-logs/.../started.json
```

**Directory Structure**:

```
pr-logs/pull/{org}_{repo}/{pr_number}/{job_name}/{build_id}/
```

## Prow JSON API

Prow also exposes a JSON API endpoint for querying recent test jobs:

```
https://prow.ci.openshift.org/prowjobs.js
```

**Advantages**:
- **Fast discovery**: Single API call returns all recent jobs (~24-48 hours)
- **Rich metadata**: PR info, job states, GCS paths included
- **Real-time**: Updates as jobs complete
- **Pre-filtered**: Know job state before downloading artifacts

**Use Cases**:
- Continuous monitoring of test runs
- Efficient discovery without GCS directory listings
- Real-time dashboards and alerting

See [Prow JSON API](api.md) for detailed documentation and integration examples.

## ci-operator

OpenShift's test orchestrator that runs within Prow pods.

**Responsibilities**:

- Build container images
- Deploy operator to test cluster
- Run e2e tests
- Collect results

**Configuration**: `openshift/release` repository

## Prowjob Object

Kubernetes CRD representing a test run.

```yaml
apiVersion: prow.k8s.io/v1
kind: ProwJob
metadata:
  name: abc-123
spec:
  type: presubmit
  job: pull-ci-...-e2e
  refs:
    org: opendatahub-io
    repo: opendatahub-operator
    pulls:
    - number: 1234
      sha: abc123
status:
  state: success  # success, failure, aborted, pending
  startTime: 2025-11-01T10:00:00Z
  completionTime: 2025-11-01T10:30:00Z
```

## GitHub Integration

**Status Checks**: Posted to PR

```
✓ opendatahub-operator-e2e
✗ opendatahub-operator-rhoai-e2e
- opendatahub-operator-e2e-hypershift (pending)
```

**Bot Comments**: `/retest`, `/test <job>`, etc.

**Merge Requirements**: All required checks must pass

## Related

- [Prow JSON API](api.md) - Fast discovery using Prow's API endpoint
- [Test Framework](test-framework.md)
- [Job Types](job-types.md)
- [GCS Artifacts](artifacts.md)

## External Links

- [Prow Documentation](https://docs.prow.k8s.io/)
- [OpenShift CI Documentation](https://docs.ci.openshift.org/)
- [ci-operator Guide](https://docs.ci.openshift.org/docs/architecture/ci-operator/)
