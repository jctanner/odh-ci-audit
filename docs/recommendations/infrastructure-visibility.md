# Infrastructure Visibility

## Priority: 4

**Impact**: High - Developer clarity and trust in CI results
**Effort**: Low - Dashboard and status badge implementation
**Cost**: Minimal (hosting/compute for dashboard)
**Timeline**: 1-2 weeks

## Problem Statement

### Current State: Developers Can't Distinguish Infrastructure from Code Failures

**Typical developer experience**:

```
Developer sees: ❌ "opendatahub-operator-e2e failed"

Questions:
- Is this my code or infrastructure?
- Should I investigate or just retry?
- Is the cluster healthy right now?
- Is this a known flaky test?
- Should I wait for better infrastructure conditions?

Result: Waste time investigating infrastructure issues
```

**Data from CI Audit**:

| Metric | Value | Impact |
|--------|-------|--------|
| **Infrastructure failure rate** | **87.6%** | Most failures aren't code issues |
| **Time-of-day variance** | **21%** (50% → 70% success) | Success depends on when you submit |
| **Flaky tests** | **99.6%** of failures | Non-deterministic results |
| **Manual retries required** | **75.4%** of PRs | Can't tell if retry will help |

**Problem**: Developers have no visibility into **why** tests fail or **when** to trust results.

## Solution: Multi-Layer Infrastructure Visibility

Provide developers with clear signals about infrastructure health and failure causes.

### Layer 1: PR Status Badges (Most Important)

**Current PR Status**:
```
❌ pull-ci-opendatahub-operator-e2e — Failed
```

**Improved PR Status**:
```
⚠️ pull-ci-opendatahub-operator-e2e — Infrastructure Timeout (Auto-retry in 5m)
❌ pull-ci-opendatahub-operator-e2e — Code Failure: Test assertion failed
✓ pull-ci-opendatahub-operator-e2e — Passed (retry 2/2)
```

### Layer 2: Infrastructure Health Dashboard

Real-time cluster health visible to all developers:

```
┌─────────────────────────────────────────────────────────┐
│ Prow Cluster Health - opendatahub-operator             │
├─────────────────────────────────────────────────────────┤
│ Overall Status: ⚠️ DEGRADED (52% success rate)          │
│ Current Time: 3:15 PM UTC (10:15 AM EST / 11:15 AM EDT)│
│                                                         │
│ ⚠️  Peak Hour Warning                                   │
│     Success rate drops to 52-58% during 1-4 PM UTC     │
│     Recommendation: Wait until 5 PM UTC for best results│
│                                                         │
│ Cluster Resources:                                      │
│   CPU:    [████████░░] 78% allocated                    │
│   Memory: [█████████░] 85% allocated                    │
│   Nodes:  12/15 ready (3 not ready)                    │
│                                                         │
│ Recent Infrastructure Issues:                           │
│   🔴 High timeout rate (last hour): 45%                 │
│   🔴 Image pull failures: 12 in last hour               │
│   🟡 Pod startup delays: avg 8.2 min (normal: 2 min)   │
│                                                         │
│ Test Success Rate by Time:                             │
│   5-7 AM UTC:   70.8% ✓ (best time)                    │
│   9 AM-12 PM:   58.3% ⚠️                                │
│   1-4 PM UTC:   52.6% 🔴 (current - worst time)        │
│   5-8 PM UTC:   61.2% ⚠️                                │
│                                                         │
│ Known Flaky Tests (>70% failure rate):                 │
│   • TestOdhOperator: 81.5% flake rate                  │
│   • cluster install: overall: 91.9% flake rate         │
│   • TestOdhOperator/services: 62.5% flake rate         │
└─────────────────────────────────────────────────────────┘
```

### Layer 3: Per-Test Flake Metrics

Show flake rate directly on test results:

```
❌ TestOdhOperator failed

⚠️ This test has 81.5% flake rate (4,378 failures, 995 passes)
   This failure is likely NOT related to your code changes.

   Infrastructure issues in this test:
   - 69.5% of failures: Timeouts waiting for pods
   - 51.3% of failures: Pod startup issues
   - 17.6% of failures: Image pull errors

   Recommendation: Auto-retry will run in 5 minutes
```

## Implementation

### Part 1: Enhanced PR Status Badges

Modify Prow reporting to include failure classification:

**File**: Prow webhook configuration or custom reporter

```go
package reporter

import (
    "strings"
)

// ClassifyFailure determines if failure is infrastructure or code-related
func ClassifyFailure(testResult TestResult) FailureType {
    failureMsg := strings.ToLower(testResult.FailureMessage)

    // Infrastructure patterns
    infraPatterns := []string{
        "timeout",
        "timed out",
        "deadline exceeded",
        "imagepullbackoff",
        "errimagepull",
        "pod not ready",
        "connection refused",
        "dial tcp",
        "[infrastructure]",  // From fail-fast checks
    }

    for _, pattern := range infraPatterns {
        if strings.Contains(failureMsg, pattern) {
            return InfrastructureFailure
        }
    }

    // Code patterns
    codePatterns := []string{
        "panic",
        "nil pointer",
        "assertion failed",
        "expected",  // Ginkgo assertions
    }

    for _, pattern := range codePatterns {
        if strings.Contains(failureMsg, pattern) {
            return CodeFailure
        }
    }

    return UnknownFailure
}

// GenerateStatusMessage creates enhanced status message
func GenerateStatusMessage(testResult TestResult) string {
    classification := ClassifyFailure(testResult)

    switch classification {
    case InfrastructureFailure:
        if testResult.WillAutoRetry {
            return fmt.Sprintf("⚠️ %s — Infrastructure Timeout (Auto-retry in %s)",
                testResult.JobName, testResult.RetryDelay)
        }
        return fmt.Sprintf("⚠️ %s — Infrastructure Issue: %s",
            testResult.JobName, ExtractErrorSummary(testResult.FailureMessage))

    case CodeFailure:
        return fmt.Sprintf("❌ %s — Code Failure: %s",
            testResult.JobName, ExtractErrorSummary(testResult.FailureMessage))

    case UnknownFailure:
        return fmt.Sprintf("❌ %s — Failed: %s",
            testResult.JobName, ExtractErrorSummary(testResult.FailureMessage))
    }
}

// ExtractErrorSummary pulls concise error from full message
func ExtractErrorSummary(fullMessage string) string {
    // Extract first line or first 100 chars
    lines := strings.Split(fullMessage, "\n")
    if len(lines) > 0 {
        summary := lines[0]
        if len(summary) > 100 {
            return summary[:97] + "..."
        }
        return summary
    }
    return "Unknown error"
}
```

**GitHub Status Check Update**:

```go
// Post to GitHub with enhanced status
func PostGitHubStatus(pr int, testResult TestResult) error {
    status := &github.RepoStatus{
        State:       getState(testResult),
        Context:     github.String(testResult.JobName),
        Description: github.String(GenerateStatusMessage(testResult)),
        TargetURL:   github.String(testResult.LogsURL),
    }

    // Add infrastructure health indicator
    if classification == InfrastructureFailure {
        // Add label or annotation showing current cluster health
        clusterHealth := GetCurrentClusterHealth()
        status.Description = github.String(fmt.Sprintf("%s (Cluster: %s)",
            GenerateStatusMessage(testResult), clusterHealth))
    }

    _, _, err := githubClient.Repositories.CreateStatus(ctx, org, repo, sha, status)
    return err
}
```

### Part 2: Infrastructure Health Dashboard

Create a dashboard showing real-time cluster metrics:

**Tech Stack**:
- Backend: Go service querying Prometheus/cluster API
- Frontend: React + Recharts for visualization
- Update frequency: Every 30 seconds

**Key Metrics to Display**:

```go
type ClusterHealth struct {
    OverallStatus   string  // "HEALTHY", "DEGRADED", "DOWN"
    SuccessRate     float64 // Last hour success rate
    CPUAllocation   float64 // % of CPU allocated
    MemoryAllocation float64 // % of memory allocated
    ReadyNodes      int
    TotalNodes      int

    // Hourly success rates for 24h
    HourlySuccessRates []HourlyRate

    // Current issues
    TimeoutRate     float64 // % of tests timing out (last hour)
    ImagePullErrors int     // Count in last hour
    PodStartupDelay float64 // Average pod startup time (last hour)

    // Top flaky tests
    TopFlakyTests []FlakyTest
}

type HourlyRate struct {
    Hour        int     // 0-23 UTC
    SuccessRate float64
}

type FlakyTest struct {
    Name        string
    FlakeRate   float64 // %
    Failures    int
    Passes      int
}
```

**Dashboard API Endpoint**:

```go
// GET /api/cluster-health
func GetClusterHealth(w http.ResponseWriter, r *http.Request) {
    health := ClusterHealth{
        OverallStatus:    calculateOverallStatus(),
        SuccessRate:      getSuccessRateLast Hour(),
        CPUAllocation:    getCPUAllocation(),
        MemoryAllocation: getMemoryAllocation(),
        ReadyNodes:       getReadyNodeCount(),
        TotalNodes:       getTotalNodeCount(),
        HourlySuccessRates: getHourlySuccessRates(),
        TimeoutRate:      getTimeoutRate(),
        ImagePullErrors:  getImagePullErrorCount(),
        PodStartupDelay:  getAvgPodStartupDelay(),
        TopFlakyTests:    getTopFlakyTests(10),
    }

    json.NewEncoder(w).Encode(health)
}

func calculateOverallStatus() string {
    successRate := getSuccessRateLast Hour()
    if successRate >= 70 {
        return "HEALTHY"
    } else if successRate >= 50 {
        return "DEGRADED"
    } else {
        return "DOWN"
    }
}
```

**Frontend Dashboard** (`dashboard.tsx`):

```tsx
import React, { useEffect, useState } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';

function ClusterHealthDashboard() {
    const [health, setHealth] = useState<ClusterHealth | null>(null);

    useEffect(() => {
        const fetchHealth = async () => {
            const response = await fetch('/api/cluster-health');
            const data = await response.json();
            setHealth(data);
        };

        fetchHealth();
        const interval = setInterval(fetchHealth, 30000); // Update every 30s
        return () => clearInterval(interval);
    }, []);

    if (!health) return <div>Loading...</div>;

    return (
        <div className="dashboard">
            <h1>Prow Cluster Health - opendatahub-operator</h1>

            {/* Overall Status */}
            <div className={`status-badge ${health.overallStatus.toLowerCase()}`}>
                {health.overallStatus} ({health.successRate.toFixed(1)}% success rate)
            </div>

            {/* Peak Hour Warning */}
            {isPeakHour() && (
                <div className="warning-banner">
                    ⚠️ Peak Hour Warning: Success rate drops to 52-58% during 1-4 PM UTC
                </div>
            )}

            {/* Resource Usage */}
            <div className="resource-section">
                <h2>Cluster Resources</h2>
                <ProgressBar label="CPU" value={health.cpuAllocation} />
                <ProgressBar label="Memory" value={health.memoryAllocation} />
                <div>Nodes: {health.readyNodes}/{health.totalNodes} ready</div>
            </div>

            {/* Success Rate by Hour */}
            <div className="chart-section">
                <h2>Success Rate by Time of Day</h2>
                <LineChart width={800} height={300} data={health.hourlySuccessRates}>
                    <XAxis dataKey="hour" />
                    <YAxis domain={[0, 100]} />
                    <Tooltip />
                    <Line type="monotone" dataKey="successRate" stroke="#8884d8" />
                </LineChart>
            </div>

            {/* Top Flaky Tests */}
            <div className="flaky-tests-section">
                <h2>Known Flaky Tests (&gt;70% failure rate)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Test Name</th>
                            <th>Flake Rate</th>
                            <th>Failures</th>
                            <th>Passes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {health.topFlakyTests.map((test) => (
                            <tr key={test.name}>
                                <td>{test.name}</td>
                                <td>{test.flakeRate.toFixed(1)}%</td>
                                <td>{test.failures}</td>
                                <td>{test.passes}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
```

### Part 3: Per-Test Flake Annotations

Add flake rate information directly to test failure output:

**In Prow Reporter**:

```go
// After test failure, look up flake rate and annotate
func AnnotateWithFlakeData(testName string, failureMessage string) string {
    flakeData := GetTestFlakeRate(testName)

    if flakeData.FlakeRate > 70 {
        annotation := fmt.Sprintf(`
⚠️ This test has %.1f%% flake rate (%d failures, %d passes)
   This failure is likely NOT related to your code changes.

   Infrastructure issues in this test:
   - %.1f%% of failures: %s

   Recommendation: %s
`,
            flakeData.FlakeRate,
            flakeData.Failures,
            flakeData.Passes,
            flakeData.TopFailurePatternPct,
            flakeData.TopFailurePattern,
            getRecommendation(flakeData),
        )

        return annotation + "\n\nOriginal error:\n" + failureMessage
    }

    return failureMessage
}

func getRecommendation(flakeData FlakeData) string {
    if flakeData.FlakeRate > 80 {
        return "Auto-retry will run. This test is known to be very flaky."
    } else if flakeData.FlakeRate > 50 {
        return "Consider retrying if this persists."
    }
    return "Investigate this failure - flake rate is moderate."
}
```

## Dashboard Deployment

### Option 1: Prow Built-in Dashboard

Extend existing Prow Deck UI:

```
https://prow.ci.openshift.org/  → Add "Cluster Health" tab
```

### Option 2: Standalone Dashboard

Deploy separate dashboard service:

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ci-health-dashboard
  namespace: ci
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: backend
        image: quay.io/opendatahub/ci-health-dashboard:latest
        ports:
        - containerPort: 8080
        env:
        - name: PROMETHEUS_URL
          value: "http://prometheus.ci.svc:9090"
        - name: DATABASE_URL
          value: "postgresql://ci_audit:password@postgres.ci.svc/ci_audit"

      - name: frontend
        image: quay.io/opendatahub/ci-health-dashboard-ui:latest
        ports:
        - containerPort: 3000

---
apiVersion: v1
kind: Service
metadata:
  name: ci-health-dashboard
spec:
  ports:
  - port: 80
    targetPort: 3000
  selector:
    app: ci-health-dashboard

---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: ci-health
spec:
  host: ci-health.opendatahub.io
  to:
    kind: Service
    name: ci-health-dashboard
```

Access at: `https://ci-health.opendatahub.io`

## Success Metrics

Track adoption and effectiveness:

1. **Dashboard Usage**:
   - Daily active users
   - Page views
   - Average time on page

2. **Developer Behavior**:
   - Reduction in "investigation time" before retry
   - Correlation between bad cluster health and manual retries

3. **Trust in CI**:
   - Survey: "I can tell when CI failures are infrastructure vs my code"
   - Survey: "I know when is the best time to submit PRs"

## Rollout Plan

### Week 1: PR Status Badges

1. Implement failure classification logic
2. Deploy enhanced status message generation
3. Test on 10-20 PRs
4. Gather developer feedback

### Week 2: Dashboard Backend

1. Build API endpoints for cluster health
2. Connect to Prometheus and database
3. Test data accuracy

### Week 3: Dashboard Frontend

1. Build React dashboard UI
2. Deploy to staging
3. Internal beta testing

### Week 4: Flake Annotations

1. Add per-test flake rate lookup
2. Annotate failure messages
3. Full rollout

## Related Documentation

- [Flake Metrics Dashboard](flake-metrics.md) - Detailed flake tracking
- [Auto-Retry Configuration](auto-retry-configuration.md) - Show retry status
- [Fail-Fast Patterns](fail-fast-patterns.md) - Generate [INFRASTRUCTURE] labels
- [Flake Rate Analysis](../findings/flake-rate.md) - Data source for flake rates
