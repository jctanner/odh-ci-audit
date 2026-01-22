# Prow CI Infrastructure Analysis

Analysis based on 1053 build logs collected from opendatahub-operator e2e tests.

## Infrastructure Stack

### Build Orchestration
- **Platform**: ci-operator (version v20251124-ba75e58c2 as of Nov 2024)
- **Build Cluster**: `build08` (likely part of build01-buildNN fleet)
- **Namespace**: `ci-op-{random}` (e.g., `ci-op-kqf787cx`)
- **Console**: https://console.build08.ci.openshift.org/k8s/cluster/projects/ci-op-{namespace}

### Test Cluster Provisioning

**Cloud Provider**: Google Cloud Platform (GCP)
- **Cluster Profile**: `gcp-opendatahub`
- **Region**: `us-central1`
- **Lease System**: `gcp-opendatahub-quota-slice` (resource quota management)
- **Lease Example**: `us-central1--gcp-opendatahub-quota-slice-00`

**Installation Method**: IPI (Installer Provisioned Infrastructure)
- Uses OpenShift's automated installer
- Ephemeral clusters created per-test
- **Installation Time**: ~40 minutes (step "ipi-install-install")

**OpenShift Version**:
- **Test Version**: 4.19.19 (as of Nov 2024)
- **Release Stream**: `stable-4.19`
- **Source**: quay.io/openshift-release-dev/ocp-release
- **Images**: 189 container images imported per release

### Test Execution Pipeline

**Multi-Stage Test Steps** (in order):
1. **Configuration Phase** (~21 seconds):
   - `ipi-conf` - Base configuration
   - `ipi-conf-telemetry` - Telemetry setup
   - `ipi-conf-gcp` - GCP-specific config

2. **Pre-Install Phase** (~29 seconds):
   - `ipi-install-monitoringpvc` - Monitoring PVCs
   - `ipi-install-rbac` - RBAC configuration
   - `openshift-cluster-bot-rbac` - Bot permissions
   - `ipi-install-hosted-loki` - Loki logging

3. **Cluster Install** (~40 minutes):
   - `ipi-install-install` - Full OpenShift cluster provisioning

4. **Validation Phase** (~2 minutes):
   - `ipi-install-times-collection` - Collect metrics
   - `nodes-readiness` - Verify nodes ready
   - `multiarch-validate-nodes` - Architecture validation

5. **Test Execution** (~variable):
   - e2e tests run via Ginkgo framework
   - Tests deploy and validate ODH components

### Build Pipeline

**Source to Image**:
1. Clone source: `github.com/opendatahub-io/opendatahub-operator`
2. Merge PR branch into main
3. Build images (~3-5 minutes each):
   - `src` - Source code image
   - `opendatahub-operator` - Main operator image
   - `opendatahub-operator-rhoai` - RHOAI variant
   - `opendatahub-operator-bundle` - Bundle image

**Base Images**:
- **Go Build**: `openshift/release:rhel-9-release-golang-1.24-openshift-4.20`
- **Operator SDK**: `ocp/cli-operator-sdk:v1.39.2`
- **Runtime**: `ocp/ubi-minimal:9`
- **UPI Installers**: Multiple versions (4.5, 4.12, 4.14, 4.16)

**Registry**:
- Internal: `ci-op-{namespace}/pipeline:{image-name}`
- Proxy: `quay-proxy.ci.openshift.org`
- Output: Tagged to `stable:opendatahub-operator`

### Resource Management

**Quota System**:
- Leases acquired from quota slices
- Prevents resource exhaustion
- Enables fair sharing of GCP quotas

**Timeouts**:
- **Test Timeout**: 8 hours
- **Grace Period**: 1 hour
- **Cluster Install**: ~40 minutes average

### Test Components Deployed

**Required Operators** (installed by e2e tests):
- openshift-cert-manager-operator
- cluster-observability-operator
- tempo-product
- opentelemetry-product
- rhcl-operator
- job-set operator
- leader-worker-set operator

**ODH Components Tested**:
- Dashboard (managed)
- KServe (v0.15)
- Feast Operator (v0.57.0)
- Model Registry (Kubeflow + ODH variants)
- Llama Stack Operator (v0.4.0)
- Training Operator (v1.9.0)
- Kubeflow Trainer (v2.1.0)
- Workbenches (Notebook Controller v1.10.0)

**Components Removed/Skipped**:
- AI Pipelines (kubeflow pipelines)
- Kueue
- Ray
- TrustyAI

### Common Failure Patterns

From the build logs, we observed:

**RBAC Permission Errors**:
- Service account lacking required cluster roles
- Attempting to grant permissions not held
- Common with: dashboard, kserve, modelcontroller, trainer

**Timing Issues**:
- Components not ready within timeout
- Dependencies not fully deployed
- Webhooks not responding

**Infrastructure**:
- GCS bucket upload failures
- Image pull errors
- Network connectivity issues
- Node not ready states

### Data Retention

**GCS Bucket**: `test-platform-results`
- **Retention**: ~6 months (as of Jan 2026)
- **Oldest Data**: July 2025
- **Path**: `pr-logs/pull/{org}_{repo}/{pr}/{job}/{build_id}/`

## Architecture Diagram

```
GitHub PR
    ↓
Prow Webhook
    ↓
Build Cluster (build08)
    ├─ ci-operator pod
    ├─ Build images (~5 min)
    └─ Acquire GCP lease
        ↓
    GCP us-central1
        ├─ Provision OpenShift 4.19 (~40 min)
        ├─ Deploy ODH components
        ├─ Run e2e tests (Ginkgo)
        └─ Upload artifacts to GCS
            ↓
        test-platform-results bucket
            ├─ started.json
            ├─ finished.json
            ├─ prowjob.json
            ├─ build-log.txt
            └─ artifacts/junit*.xml
```

## Cluster Lifecycle

**Total Time**: ~1-2 hours per test run
- Lease acquisition: <1 min
- Image builds: ~5 min
- Cluster provision: ~40 min
- Tests execution: ~variable (5-60 min)
- Cleanup: automatic

**Cost Implications**:
- ~18,000 test runs collected
- Each run = 1-2 hours GCP compute
- Significant cloud costs for CI infrastructure
- Justifies quota management system

## Key Findings

1. **Fully Automated**: End-to-end automation from PR to results
2. **Ephemeral**: Fresh cluster per test (no state contamination)
3. **Scalable**: Quota system enables parallel execution
4. **Observable**: Comprehensive logging to GCS
5. **Complex**: 40+ minute cluster setup before tests run
6. **Expensive**: Ephemeral GCP clusters for each test

## Future Analysis Opportunities

With this infrastructure knowledge, we can:
- Correlate failures with OpenShift version changes
- Identify lease/quota bottlenecks
- Detect infrastructure vs. code failures
- Track cluster provisioning time trends
- Analyze component deployment patterns
