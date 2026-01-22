# Most Common Failures

## Overview

Analysis of the most frequently occurring test failures.

## Top Failing Tests

```sql
-- Top 20 tests by failure count
SELECT
    test_suite,
    test_name,
    COUNT(*) as total_executions,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures,
    SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes,
    ROUND(100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 1) as failure_rate
FROM test_cases
GROUP BY test_suite, test_name
HAVING failures > 0
ORDER BY failures DESC
LIMIT 20;
```

**Top 10 Most Failing Tests**:

| Test Suite | Test Name | Executions | Failures | Pass Rate |
|------------|-----------|-----------|----------|-----------|
| e2e-test | **TestOdhOperator** | 5,373 | 4,378 | **18.5%** |
| step graph | Run multi-stage test test phase | 8,157 | 2,905 | 64.4% |
| step graph | Run...opendatahub-operator-e2e-e2e... | 3,489 | 2,250 | 35.5% |
| step graph | Clone the correct source code... | 20,486 | 2,164 | 89.4% |
| e2e-test | TestOdhOperator/services | 2,803 | 1,753 | 37.5% |
| e2e-test | TestOdhOperator/components | 3,174 | 1,743 | 45.1% |
| e2e-test | TestOdhOperator/services/group_1 | 2,439 | 1,585 | 35.0% |
| e2e-test | TestOdhOperator/services/group_1/monitoring | 2,308 | 1,399 | 39.4% |
| step graph | Build image opendatahub-operator... | 17,830 | 1,246 | 93.0% |
| step graph | Run multi-stage test pre phase | 9,270 | 1,113 | 88.0% |

**Critical Finding**: `TestOdhOperator` alone accounts for **11.2% of ALL test failures** (4,378 out of 39,117), with an 81.5% failure rate. This single test is the primary driver of CI failures.

## Top Failure Messages

```sql
-- Most common failure messages
SELECT
    LEFT(failure_message, 100) as message,
    COUNT(*) as occurrences,
    COUNT(DISTINCT test_name) as affected_tests
FROM test_cases
WHERE status = 'failed'
    AND failure_message IS NOT NULL
    AND failure_message != ''
GROUP BY LEFT(failure_message, 100)
ORDER BY occurrences DESC
LIMIT 20;
```

**Top 20 Failure Messages**:

| Failure Message | Occurrences | Affected Tests |
|-----------------|-------------|----------------|
| Test TestOdhOperator failed | 4,378 | 1 |
| Test TestOdhOperator/services failed | 1,753 | 1 |
| Test TestOdhOperator/components failed | 1,743 | 1 |
| Test TestOdhOperator/services/group_1 failed | 1,585 | 1 |
| Test TestOdhOperator/services/group_1/monitoring failed | 1,399 | 1 |
| Test TestOdhOperator/components/group_1 failed | 971 | 1 |
| Test TestOdhOperator/components/group_1/trainer failed | 746 | 1 |
| Test TestOdhOperator/DSCInitialization_and_DataScienceCluster_management_E2E_Tests/Ensure_required_o... | 682 | 11 |
| Test TestOdhOperator/DSCInitialization_and_DataScienceCluster_management_E2E_Tests failed | 614 | 1 |
| Test TestOdhOperator/components/group_2 failed | 366 | 1 |
| Test TestOdhOperator/components/group_2/kueue failed | 354 | 1 |
| **Operator unavailable (null): operator is not reporting conditions** | **330** | **34** |
| Test TestOdhOperator/components/group_1/trainer/Validate_component_releases failed | 318 | 1 |
| Test TestOdhOperator/services/group_1/monitoring/Test_Metrics_TLS_is_always_enabled_for_Prometheus_e... | 300 | 1 |
| Test TestOdhOperator/DSCInitialization_and_DataScienceCluster_management_E2E_Tests/Ensure_required_r... | 282 | 1 |
| Test TestOdhOperator/components/group_1/kserve failed | 254 | 1 |
| Test TestOdhOperator/services/group_1/monitoring/Test_Prometheus_rules_lifecycle failed | 254 | 1 |
| Test TestOdhOperator/components/group_2/kueue/Validate_component_removed_to_unmanaged_transition failed | 241 | 1 |
| Test TestOdhOperator/services/group_1/gateway failed | 234 | 1 |
| Test TestOdhOperator/components/group_1/trainer/Validate_external_operator_degraded_condition_monitor... | 223 | 5 |

**Key Observations**:

1. **TestOdhOperator dominates**: The top 10 failure messages are all variations of TestOdhOperator test hierarchies, accounting for over 12,000 failures combined.

2. **Generic failure messages**: Most messages are simply "Test X failed" without specific error details. This makes root cause analysis difficult without examining build logs.

3. **Operator unavailable**: The only specific error message in the top 20 is "Operator unavailable: operator is not reporting conditions" with 330 occurrences across 34 different tests. This indicates infrastructure/timing issues where operators aren't ready when tests check their status.

4. **Broad impact**: While TestOdhOperator failures affect only 1 test name (the parent test), the operator unavailable error affects 34 different tests, suggesting a systemic infrastructure problem rather than a specific test issue.

## Failure Type Distribution

```sql
-- Failure type distribution based on log content patterns
WITH failure_categorization AS (
    SELECT
        tr.build_id,
        tr.result,
        CASE
            WHEN bl.log_content LIKE '%timeout%' OR bl.log_content LIKE '%timed out%' OR bl.log_content LIKE '%deadline exceeded%'
                 OR bl.log_content LIKE '%ImagePull%' OR bl.log_content LIKE '%pull image%'
                 OR bl.log_content LIKE '%connection refused%' OR bl.log_content LIKE '%dial tcp%'
                 OR bl.log_content LIKE '%pod%not%ready%' OR bl.log_content LIKE '%waiting for pods%'
            THEN 'Infrastructure'
            WHEN bl.log_content LIKE '%panic%' OR bl.log_content LIKE '%nil pointer%' OR bl.log_content LIKE '%assertion failed%'
            THEN 'Code Regression'
            WHEN bl.log_content LIKE '%config%' OR bl.log_content LIKE '%YAML%' OR bl.log_content LIKE '%permission denied%'
            THEN 'Configuration'
            WHEN bl.log_content LIKE '%CRD%' OR bl.log_content LIKE '%webhook%' OR bl.log_content LIKE '%operator%unavailable%'
            THEN 'Dependency'
            ELSE 'Unknown/Other'
        END as failure_type
    FROM build_logs bl
    JOIN test_runs tr ON bl.run_id = tr.id
    WHERE tr.result = 'FAILURE'
        AND bl.log_content IS NOT NULL
)
SELECT
    failure_type,
    COUNT(*) as failures,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as percentage
FROM failure_categorization
GROUP BY failure_type
ORDER BY failures DESC;
```

**Actual Breakdown** (based on build log analysis):

| Failure Type | Failures | Percentage |
|--------------|----------|------------|
| **Infrastructure** | **3,673** | **87.6%** |
| Configuration | 514 | 12.3% |
| Code Regression | 4 | 0.1% |
| Unknown/Other | 3 | 0.1% |

**Critical Finding**: **87.6% of all failures are infrastructure-related** (timeouts, image pulls, network issues, pod startup problems). This dramatically differs from initial expectations and confirms findings from [Infrastructure Issues](infrastructure.md) and [Same-SHA Analysis](same-sha-analysis.md).

**Analysis**:

1. **Infrastructure dominates**: Nearly 9 out of 10 failures are caused by infrastructure problems, not code defects. This aligns with the 95% flake rate found in same-SHA analysis.

2. **Minimal code regressions**: Only 4 failures (0.1%) show clear signs of code issues (panics, nil pointers, assertion failures). This proves that the CI system is failing to catch real bugs because it's drowning in infrastructure noise.

3. **Configuration issues**: 12.3% of failures involve configuration, YAML parsing, or permission issues. Many of these may be infrastructure-related (e.g., permissions on infrastructure resources).

4. **Missing categories**: The initial expectation of 20-30% test flakes as a separate category is misleading - test flakes ARE infrastructure failures. The 87.6% infrastructure rate encompasses both pure infrastructure problems and infrastructure-triggered test flakes.

5. **CI effectiveness**: With only 0.1% code regression detection, the CI system is spending 99.9% of its failure budget on environmental issues rather than catching bugs.

## Component-Specific Failures

### Component Overview

**Failure statistics by component**:

| Component | Total Tests | Failures | Passes | Failure Rate |
|-----------|-------------|----------|--------|--------------|
| Monitoring | 81,772 | 3,151 | 78,621 | 3.9% |
| Trainer | 19,428 | 1,904 | 17,524 | 9.8% |
| Kueue | 40,982 | 846 | 40,136 | 2.1% |
| DataSciencePipelines | 118,831 | 710 | 118,121 | 0.6% |
| KServe | 41,108 | 658 | 40,450 | 1.6% |
| Gateway | 10,111 | 527 | 9,584 | 5.2% |
| Dashboard | 51,379 | 295 | 51,084 | 0.6% |
| ModelRegistry | 35,708 | 243 | 35,465 | 0.7% |

**Key Observations**:

- **Trainer has highest failure rate** at 9.8%, followed by Gateway (5.2%) and Monitoring (3.9%)
- **Dashboard, DSP, and ModelRegistry are most reliable** with <1% failure rates
- **Volume vs. rate**: Monitoring has the most total failures (3,151) but only 3.9% rate due to high test volume

### Dashboard

**Statistics**: 51,379 total tests, 295 failures (0.6% failure rate)

**Top 10 Failing Dashboard Tests**:

| Test Name | Executions | Failures | Failure Rate |
|-----------|------------|----------|--------------|
| TestOdhOperator/components/group_1/dashboard | 109 | 109 | 100.0% |
| TestOdhOperator/components/group_1/dashboard/Validate_component_enabled | 80 | 80 | 100.0% |
| TestOdhOperator/components/dashboard | 26 | 26 | 100.0% |
| TestOdhOperator/components/group_1/dashboard/Validate_CRDs_reinstated | 16 | 16 | 100.0% |
| TestOdhOperator/components/dashboard/Validate_component_enabled | 14 | 14 | 100.0% |
| TestOdhOperator/components/group_1/dashboard/Validate_update_operand_resources | 13 | 13 | 100.0% |
| TestOdhOperator/components/dashboard/Validate_CRDs_reinstated/acceleratorprofiles... | 12 | 12 | 100.0% |
| TestOdhOperator/components/dashboard/Validate_CRDs_reinstated | 12 | 12 | 100.0% |
| TestOdhOperator/components/group_1/dashboard/Validate_update_operand_resources/deployment_odh-dashboard | 10 | 10 | 100.0% |
| TestOdhOperator/components/group_1/dashboard/Validate_update_operand_resources/deployment_rhods-dashboard | 3 | 3 | 100.0% |

**Analysis**:

- **100% failure rate**: All failing Dashboard tests have a 100% failure rate, indicating these specific tests consistently fail
- **Low absolute volume**: Only 295 total failures despite 51,379 test executions shows Dashboard component is generally reliable
- **Parent test failures cascade**: TestOdhOperator/components/group_1/dashboard fails 100% of the time (109 failures), likely causing all child tests to fail as well
- **Common patterns**: Failures cluster around component enablement validation, CRD reinstallation, and operand resource updates
- **Infrastructure vs. code**: The 100% failure rate suggests either the tests are broken/disabled, or there's a systemic issue with Dashboard test setup that's unrelated to the Dashboard component code itself

### KServe

**Statistics**: 41,108 total tests, 658 failures (1.6% failure rate)

**Top 10 Failing KServe Tests**:

| Test Name | Executions | Failures | Failure Rate |
|-----------|------------|----------|--------------|
| TestOdhOperator/components/group_1/kserve | 254 | 254 | 100.0% |
| TestOdhOperator/components/group_1/kserve/Validate_component_enabled | 153 | 153 | 100.0% |
| TestOdhOperator/components/kserve | 75 | 75 | 100.0% |
| TestOdhOperator/components/group_1/kserve/Validate_VAP_created_when_kserve_is_enabled | 72 | 72 | 100.0% |
| TestOdhOperator/components/kserve/Validate_component_enabled | 64 | 64 | 100.0% |
| TestOdhOperator/components/group_1/kserve/Validate_well-known_LLMInferenceServiceConfig_versioning | 20 | 20 | 100.0% |
| TestOdhOperator/components/group_1/kserve/Validate_component_disabled | 9 | 9 | 100.0% |
| TestOdhOperator/components/kserve/Validate_connection_webhook_injection | 4 | 4 | 100.0% |
| TestOdhOperator/components/kserve/Validate_VAP_created_when_kserve_is_enabled | 4 | 4 | 100.0% |
| TestOdhOperator/components/kserve/Setup_Serverless | 3 | 3 | 100.0% |

**Analysis**:

- **Identical pattern to Dashboard**: All failing KServe tests have 100% failure rate
- **Low overall impact**: 1.6% failure rate overall (658 out of 41,108 tests)
- **Parent test cascades**: TestOdhOperator/components/group_1/kserve (254 failures) likely causes child test failures
- **Test coverage areas**: Failures span component enablement, ValidatingAdmissionPolicy (VAP) creation, LLM inference config versioning, and serverless setup
- **Likely test infrastructure issue**: The 100% consistency suggests these tests are fundamentally broken or disabled, not experiencing intermittent failures

### Data Science Pipelines

**Statistics**: 118,831 total tests, 710 failures (0.6% failure rate)

**Top 10 Failing DataSciencePipelines Tests**:

| Test Name | Executions | Failures | Failure Rate |
|-----------|------------|----------|--------------|
| TestOdhOperator/components/group_1/datasciencepipelines | 99 | 99 | 100.0% |
| TestOdhOperator/components/group_1/datasciencepipelines/Validate_component_enabled | 56 | 56 | 100.0% |
| TestOdhOperator/components/group_1/datasciencepipelines/Validate_component_disabled | 39 | 39 | 100.0% |
| TestOdhOperator/components/datasciencepipelines/Validate_resource_deletion_recovery/Deployment_deletion_recovery/deployment_data-science-pipelines-operator-controller-manager | 2 | 2 | 100.0% |
| TestOdhOperator/components/group_1/datasciencepipelines/Validate_resource_deletion_recovery | 2 | 2 | 100.0% |
| TestOdhOperator/components/group_1/datasciencepipelines/Validate_update_operand_resources/deployment_data-science-pipelines-operator-controller-manager | 2 | 2 | 100.0% |
| TestOdhOperator/components/datasciencepipelines/Validate_resource_deletion_recovery | 2 | 2 | 100.0% |
| TestOdhOperator/components/datasciencepipelines/Validate_resource_deletion_recovery/Deployment_deletion_recovery | 2 | 2 | 100.0% |
| TestOdhOperator/components/group_1/datasciencepipelines/Validate_update_operand_resources | 2 | 2 | 100.0% |
| TestOdhOperator/components/datasciencepipelines | 2 | 2 | 100.0% |

**Analysis**:

- **Best overall reliability**: Tied with Dashboard at 0.6% failure rate (710 out of 118,831 tests)
- **Highest test volume**: 118,831 total test executions - most tested component
- **Same 100% pattern**: All failing tests show 100% failure rate, matching Dashboard and KServe
- **Test focus areas**: Component enablement/disablement, resource deletion recovery, operand resource updates, deployment controller manager validation
- **Very low failure count**: Despite being the most-tested component, has only 710 failures total
- **Production readiness indicator**: The 0.6% failure rate suggests DataSciencePipelines component code is highly stable, with failures limited to specific test infrastructure issues

### Model Registry

**Statistics**: 35,708 total tests, 243 failures (0.7% failure rate)

**Top 10 Failing ModelRegistry Tests**:

| Test Name | Executions | Failures | Failure Rate |
|-----------|------------|----------|--------------|
| TestOdhOperator/components/group_1/modelregistry | 81 | 81 | 100.0% |
| TestOdhOperator/components/group_1/modelregistry/Validate_component_enabled | 60 | 60 | 100.0% |
| TestOdhOperator/components/modelregistry | 19 | 19 | 100.0% |
| TestOdhOperator/components/modelregistry/Validate_resource_deletion_recovery | 15 | 15 | 100.0% |
| TestOdhOperator/components/group_1/modelregistry/Validate_CRDs_reinstated | 12 | 12 | 100.0% |
| TestOdhOperator/components/modelregistry/Validate_resource_deletion_recovery/Deployment_deletion_recovery/deployment_model-registry-operator-controller-manager | 10 | 10 | 100.0% |
| TestOdhOperator/components/modelregistry/Validate_resource_deletion_recovery/Deployment_deletion_recovery | 10 | 10 | 100.0% |
| TestOdhOperator/components/modelregistry/Validate_resource_deletion_recovery/Service_deletion_recovery | 4 | 4 | 100.0% |
| TestOdhOperator/components/group_1/modelregistry/Validate_component_disabled | 4 | 4 | 100.0% |
| TestOdhOperator/components/modelregistry/Validate_update_operand_resources | 4 | 4 | 100.0% |

**Analysis**:

- **Excellent reliability**: 0.7% failure rate (243 out of 35,708 tests)
- **Consistent 100% pattern**: All failing tests match the pattern seen in other components
- **Low absolute failures**: Only 243 total failures despite 35,708 test executions
- **Test coverage**: Failures cover component enablement, CRD reinstallation, resource deletion recovery (deployments and services), and operand resource updates
- **Component stability**: The very low failure rate indicates ModelRegistry component is production-ready with stable functionality

### Cross-Component Insights

**Patterns across all components**:

1. **100% failure rate for failing tests**: When a test fails, it fails consistently (100% of attempts). This is the opposite of flaky behavior and suggests:
    - Tests are deterministically broken or skipped
    - Specific test infrastructure setup issues
    - Potentially disabled tests still being reported as failures

2. **Low overall failure rates**: Most components have <2% failure rates:
    - Dashboard: 0.6%
    - DataSciencePipelines: 0.6%
    - ModelRegistry: 0.7%
    - KServe: 1.6%
    - Kueue: 2.1%

3. **Higher failure components**:
    - Monitoring: 3.9% (3,151 failures but high test volume)
    - Gateway: 5.2% (527 failures)
    - Trainer: 9.8% (1,904 failures)

4. **Test hierarchy cascades**: Parent test failures (e.g., `TestOdhOperator/components/group_1/dashboard`) cause all child tests to fail

5. **Validation test focus**: Most failing tests involve:
    - Component enablement/disablement validation
    - CRD reinstallation checks
    - Resource deletion recovery
    - Operand resource updates

**Recommendation**: The 100% failure rate pattern suggests these are not infrastructure flakes (which would show varying success/failure). These tests should be investigated to determine if they're:
- Intentionally disabled but still running
- Broken due to test infrastructure changes
- Failing due to missing prerequisites in the test environment

## Patterns and Trends

### Weekly Failure Rate by Job Type

![Job Type Failure Trends](../images/job_type_failure_trends.png)

**Analysis**: The failure rate trends broken down by job type reveal:

- **E2E tests** (standard and hypershift): Consistently high failure rates (40-70%) throughout the collection period
- **RHOAI E2E tests**: Similar pattern to standard e2e, indicating shared infrastructure challenges
- **Bundle and image jobs**: Much lower and more stable failure rates (5-20%)
- **Failure rate variance**: E2E tests show high week-to-week variability, suggesting environment-dependent failures rather than code issues
- **No clear improvement trend**: Failure rates remain relatively flat across the 6-month period, indicating systemic issues not addressed

## Related

- [Flake Rate Analysis](flake-rate.md)
- [Infrastructure Issues](infrastructure.md)
- [Failure Analysis](../analysis/failures/overview.md)
