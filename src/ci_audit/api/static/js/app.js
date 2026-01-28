/**
 * Main application logic
 */
class App {
    constructor() {
        this.currentTab = 'jobs';
        this.currentStatsTab = 'overview'; // Track stats sub-tab
        this.testRunsTable = null;
        this.testRunDetail = null;
        this.logViewer = null;
        this.queueManager = null;
        this.timelineChart = null;
        this.durationChart = null;
        this.prMetricsChart = null;
        this.failureSuiteChart = null;
        this.topFailingTestsChart = null;
        this.failureTimelineChart = null;
        this.timelineDays = 30; // Default to 30 days
        this.loadingFromHash = false;
    }

    init() {
        // Initialize components
        this.testRunsTable = new TestRunsTable('test-runs-view');
        this.testRunDetail = new TestRunDetail('test-runs-view');
        this.logViewer = new LogViewer('test-runs-view');
        this.queueManager = new QueueManager('queue-view');

        // Set up tab switching
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', (e) => {
                const tab = e.target.dataset.tab;
                this.switchTab(tab);
            });
        });

        // Set up hash change listener for browser back/forward
        window.addEventListener('hashchange', () => {
            this.loadFromHash();
        });

        // Load from hash or default view
        this.loadFromHash();
    }

    /**
     * Parse the current hash and load the appropriate view
     */
    loadFromHash() {
        this.loadingFromHash = true;
        const hash = window.location.hash.slice(1); // Remove the #

        if (!hash || hash === 'jobs') {
            this.showTestRuns();
        } else if (hash === 'queue') {
            this.switchTab('queue');
        } else if (hash === 'stats') {
            this.switchTab('stats');
        } else if (hash.startsWith('test-run/')) {
            const buildId = hash.split('/')[1];
            if (buildId) {
                this.showTestRunDetail(buildId);
            }
        } else if (hash.startsWith('log/')) {
            const parts = hash.split('/');
            const buildId = parts[1];
            const logType = parts[2];
            if (buildId && logType) {
                this.showLog(buildId, logType);
            }
        } else {
            // Unknown hash, default to test runs
            this.showTestRuns();
        }
        this.loadingFromHash = false;
    }

    /**
     * Update the URL hash without triggering hashchange event
     */
    updateHash(hash) {
        if (this.loadingFromHash) return; // Don't update hash if we're loading from it
        window.location.hash = hash;
    }

    switchTab(tabName) {
        // Update active tab button
        document.querySelectorAll('.tab-button').forEach(button => {
            button.classList.remove('active');
            if (button.dataset.tab === tabName) {
                button.classList.add('active');
            }
        });

        // Update active tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });

        const tabContent = document.getElementById(`${tabName}-tab`);
        if (tabContent) {
            tabContent.classList.add('active');
        }

        this.currentTab = tabName;

        // Update URL hash
        this.updateHash(tabName);

        // Load tab content
        if (tabName === 'jobs') {
            this.testRunsTable.render();
        } else if (tabName === 'queue') {
            this.queueManager.render();
        } else if (tabName === 'stats') {
            this.showStats();
        }
    }

    showTestRuns() {
        this.currentTab = 'jobs';
        this.updateHash('jobs');

        // Update active tab
        document.querySelectorAll('.tab-button').forEach(button => {
            button.classList.remove('active');
            if (button.dataset.tab === 'jobs') {
                button.classList.add('active');
            }
        });

        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById('jobs-tab').classList.add('active');

        this.testRunsTable.render();
    }

    showTestRunDetail(buildId) {
        this.currentTab = 'jobs';
        this.updateHash(`test-run/${buildId}`);

        // Update active tab
        document.querySelectorAll('.tab-button').forEach(button => {
            button.classList.remove('active');
            if (button.dataset.tab === 'jobs') {
                button.classList.add('active');
            }
        });

        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById('jobs-tab').classList.add('active');

        this.testRunDetail.render(buildId);
    }

    showLog(buildId, logType) {
        this.currentTab = 'jobs';
        this.updateHash(`log/${buildId}/${logType}`);

        // Update active tab
        document.querySelectorAll('.tab-button').forEach(button => {
            button.classList.remove('active');
            if (button.dataset.tab === 'jobs') {
                button.classList.add('active');
            }
        });

        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById('jobs-tab').classList.add('active');

        this.logViewer.render(buildId, logType);
    }

    async showStats() {
        const container = document.getElementById('stats-view');

        container.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <p>Loading statistics...</p>
            </div>
        `;

        try {
            const stats = await api.getStats();

            // Render stats tabs
            container.innerHTML = `
                <div class="stats-tabs">
                    <button class="stats-tab-button ${this.currentStatsTab === 'overview' ? 'active' : ''}" onclick="app.switchStatsTab('overview')">Overview</button>
                    <button class="stats-tab-button ${this.currentStatsTab === 'failures' ? 'active' : ''}" onclick="app.switchStatsTab('failures')">Failure Analysis</button>
                </div>
                <div id="stats-content"></div>
            `;

            // Render the active tab
            if (this.currentStatsTab === 'overview') {
                await this.renderOverviewTab(stats);
            } else {
                await this.renderFailuresTab();
            }
        } catch (error) {
            container.innerHTML = `
                <div class="message message-error">
                    Error loading statistics: ${error.message}
                </div>
            `;
        }
    }

    async renderOverviewTab(stats) {
        const container = document.getElementById('stats-content');

        const timeRangeLabel = this.timelineDays === 30 ? 'Last Month' :
                               this.timelineDays === 90 ? 'Last 3 Months' :
                               this.timelineDays === 180 ? 'Last 6 Months' :
                               `Last ${this.timelineDays} Days`;

        container.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <h2>Success/Failure Over Time (${timeRangeLabel})</h2>
                    <div class="timeline-range-selector">
                        <button class="range-button ${this.timelineDays === 30 ? 'active' : ''}" onclick="app.setTimelineRange(30)">1 Month</button>
                        <button class="range-button ${this.timelineDays === 90 ? 'active' : ''}" onclick="app.setTimelineRange(90)">3 Months</button>
                        <button class="range-button ${this.timelineDays === 180 ? 'active' : ''}" onclick="app.setTimelineRange(180)">6 Months</button>
                    </div>
                </div>
                <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 40px;">
                    <canvas id="timeline-chart"></canvas>
                </div>

                <h2 style="margin-top: 40px;">Total Test Duration (Hours)</h2>
                <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 40px;">
                    <canvas id="duration-chart"></canvas>
                </div>

                <h2 style="margin-top: 40px;">PR Metrics (Avg Runs per PR & Wait Time)</h2>
                <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 40px;">
                    <canvas id="pr-metrics-chart"></canvas>
                </div>

                <h2>Test Runs</h2>
                <div class="queue-stats">
                    <div class="stat-card">
                        <div class="number">${stats.test_runs.total}</div>
                        <div class="label">Total Runs</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">${stats.test_runs.success}</div>
                        <div class="label">Successful</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">${stats.test_runs.failure}</div>
                        <div class="label">Failed</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">${stats.test_runs.aborted}</div>
                        <div class="label">Aborted</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">${stats.test_runs.pass_rate}%</div>
                        <div class="label">Pass Rate</div>
                    </div>
                </div>

                <h2 style="margin-top: 40px;">Pull Requests</h2>
                <div class="queue-stats">
                    <div class="stat-card">
                        <div class="number">${stats.pull_requests.total}</div>
                        <div class="label">Total PRs</div>
                    </div>
                </div>

                <h2 style="margin-top: 40px;">Test Cases</h2>
                <div class="queue-stats">
                    <div class="stat-card">
                        <div class="number">${stats.test_cases.total}</div>
                        <div class="label">Total</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">${stats.test_cases.passed}</div>
                        <div class="label">Passed</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">${stats.test_cases.failed}</div>
                        <div class="label">Failed</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">${stats.test_cases.skipped}</div>
                        <div class="label">Skipped</div>
                    </div>
                </div>
        `;

        // Render the charts
        await this.renderTimelineChart();
        await this.renderDurationChart();
        await this.renderPRMetricsChart();
    }

    async renderFailuresTab() {
        const container = document.getElementById('stats-content');

        const timeRangeLabel = this.timelineDays === 30 ? 'Last Month' :
                               this.timelineDays === 90 ? 'Last 3 Months' :
                               this.timelineDays === 180 ? 'Last 6 Months' :
                               `Last ${this.timelineDays} Days`;

        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h2>Failure Trends Over Time (${timeRangeLabel})</h2>
                <div class="timeline-range-selector">
                    <button class="range-button ${this.timelineDays === 30 ? 'active' : ''}" onclick="app.setTimelineRange(30)">1 Month</button>
                    <button class="range-button ${this.timelineDays === 90 ? 'active' : ''}" onclick="app.setTimelineRange(90)">3 Months</button>
                    <button class="range-button ${this.timelineDays === 180 ? 'active' : ''}" onclick="app.setTimelineRange(180)">6 Months</button>
                </div>
            </div>
            <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 40px;">
                <canvas id="failure-timeline-chart"></canvas>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 40px;">
                <div>
                    <h2>Failures by Test Suite</h2>
                    <div style="background: white; padding: 20px; border-radius: 8px;">
                        <canvas id="failure-suite-chart"></canvas>
                    </div>
                </div>
                <div>
                    <h2>Top 10 Failing Tests</h2>
                    <div style="background: white; padding: 20px; border-radius: 8px;">
                        <canvas id="top-failing-tests-chart"></canvas>
                    </div>
                </div>
            </div>
        `;

        // Render the failure analysis charts
        await this.renderFailureTimelineChart();
        await this.renderFailureSuiteChart();
        await this.renderTopFailingTestsChart();
    }

    switchStatsTab(tab) {
        this.currentStatsTab = tab;
        this.showStats();
    }

    async renderTimelineChart() {
        try {
            const timelineData = await api.getTimeline(this.timelineDays);
            const ctx = document.getElementById('timeline-chart');

            // Destroy existing chart if it exists
            if (this.timelineChart) {
                this.timelineChart.destroy();
            }

            // Create new chart
            this.timelineChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: timelineData.dates,
                    datasets: [
                        {
                            label: 'Success',
                            data: timelineData.success,
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.3
                        },
                        {
                            label: 'Failure',
                            data: timelineData.failure,
                            borderColor: '#ef4444',
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            fill: true,
                            tension: 0.3
                        },
                        {
                            label: 'Aborted',
                            data: timelineData.aborted,
                            borderColor: '#f59e0b',
                            backgroundColor: 'rgba(245, 158, 11, 0.1)',
                            fill: true,
                            tension: 0.3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    aspectRatio: 2.5,
                    plugins: {
                        legend: {
                            position: 'top',
                        },
                        title: {
                            display: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            }
                        },
                        x: {
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45
                            }
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error rendering timeline chart:', error);
        }
    }

    async renderDurationChart() {
        try {
            const durationData = await api.getDuration(this.timelineDays);
            const ctx = document.getElementById('duration-chart');

            // Destroy existing chart if it exists
            if (this.durationChart) {
                this.durationChart.destroy();
            }

            // Create new stacked bar chart
            this.durationChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: durationData.dates,
                    datasets: [
                        {
                            label: 'Success',
                            data: durationData.success_hours,
                            backgroundColor: 'rgba(16, 185, 129, 0.8)',
                            borderColor: '#10b981',
                            borderWidth: 1
                        },
                        {
                            label: 'Failure',
                            data: durationData.failure_hours,
                            backgroundColor: 'rgba(239, 68, 68, 0.8)',
                            borderColor: '#ef4444',
                            borderWidth: 1
                        },
                        {
                            label: 'Aborted',
                            data: durationData.aborted_hours,
                            backgroundColor: 'rgba(245, 158, 11, 0.8)',
                            borderColor: '#f59e0b',
                            borderWidth: 1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    aspectRatio: 2.5,
                    plugins: {
                        legend: {
                            position: 'top',
                        },
                        title: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                footer: function(tooltipItems) {
                                    let total = 0;
                                    tooltipItems.forEach(item => {
                                        total += item.parsed.y;
                                    });
                                    return 'Total: ' + total.toFixed(2) + ' hours';
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            stacked: true,
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45
                            }
                        },
                        y: {
                            stacked: true,
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Hours'
                            }
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error rendering duration chart:', error);
        }
    }

    async renderPRMetricsChart() {
        try {
            const metricsData = await api.getPRMetrics(this.timelineDays);
            const ctx = document.getElementById('pr-metrics-chart');

            // Destroy existing chart if it exists
            if (this.prMetricsChart) {
                this.prMetricsChart.destroy();
            }

            // Create new line chart with dual Y-axes
            this.prMetricsChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: metricsData.dates,
                    datasets: [
                        {
                            label: 'Avg Runs per PR',
                            data: metricsData.avg_runs_per_pr,
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            fill: true,
                            tension: 0.3,
                            yAxisID: 'y-runs'
                        },
                        {
                            label: 'Avg Wait Time (min)',
                            data: metricsData.avg_wait_minutes,
                            borderColor: '#f59e0b',
                            backgroundColor: 'rgba(245, 158, 11, 0.1)',
                            fill: true,
                            tension: 0.3,
                            yAxisID: 'y-time'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    aspectRatio: 2.5,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                        },
                        title: {
                            display: false
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45
                            }
                        },
                        'y-runs': {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Avg Runs per PR'
                            },
                            ticks: {
                                stepSize: 1
                            }
                        },
                        'y-time': {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Avg Wait Time (minutes)'
                            },
                            grid: {
                                drawOnChartArea: false, // Only show grid for left axis
                            }
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error rendering PR metrics chart:', error);
        }
    }

    async setTimelineRange(days) {
        this.timelineDays = days;

        // Update charts based on active tab
        if (this.currentStatsTab === 'overview') {
            await this.renderTimelineChart();
            await this.renderDurationChart();
            await this.renderPRMetricsChart();
        } else if (this.currentStatsTab === 'failures') {
            await this.renderFailureTimelineChart();
        }

        // Update button states
        document.querySelectorAll('.range-button').forEach(btn => {
            btn.classList.remove('active');
        });
        event.target.classList.add('active');
    }

    async renderFailureTimelineChart() {
        try {
            const data = await api.getFailureTimeline(this.timelineDays);

            // Destroy existing chart if it exists
            if (this.failureTimelineChart) {
                this.failureTimelineChart.destroy();
            }

            const ctx = document.getElementById('failure-timeline-chart');
            this.failureTimelineChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.dates,
                    datasets: [{
                        label: 'Failed Tests',
                        data: data.failed_tests,
                        borderColor: '#f8d7da',
                        backgroundColor: 'rgba(248, 215, 218, 0.2)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    aspectRatio: 3,
                    plugins: {
                        legend: {
                            display: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error rendering failure timeline chart:', error);
        }
    }

    async renderFailureSuiteChart() {
        try {
            const data = await api.getFailuresBySuite();

            // Destroy existing chart if it exists
            if (this.failureSuiteChart) {
                this.failureSuiteChart.destroy();
            }

            const ctx = document.getElementById('failure-suite-chart');
            this.failureSuiteChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: data.suites,
                    datasets: [{
                        data: data.failures,
                        backgroundColor: [
                            '#667eea',
                            '#764ba2',
                            '#f093fb',
                            '#4facfe',
                            '#43e97b',
                            '#fa709a',
                            '#fee140',
                            '#30cfd0'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    aspectRatio: 1.5,
                    plugins: {
                        legend: {
                            position: 'right'
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error rendering failure suite chart:', error);
        }
    }

    async renderTopFailingTestsChart() {
        try {
            const data = await api.getTopFailingTests(10);

            // Destroy existing chart if it exists
            if (this.topFailingTestsChart) {
                this.topFailingTestsChart.destroy();
            }

            // Truncate test names for display
            const truncatedLabels = data.tests.map(name =>
                name.length > 50 ? name.substring(0, 47) + '...' : name
            );

            const ctx = document.getElementById('top-failing-tests-chart');
            this.topFailingTestsChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: truncatedLabels,
                    datasets: [{
                        label: 'Failures',
                        data: data.failures,
                        backgroundColor: '#f8d7da',
                        borderColor: '#721c24',
                        borderWidth: 1
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: true,
                    aspectRatio: 1,
                    plugins: {
                        legend: {
                            display: false
                        }
                    },
                    scales: {
                        x: {
                            beginAtZero: true
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error rendering top failing tests chart:', error);
        }
    }
}

// Initialize app when DOM is ready
let app;
let testRunsTable;
let testRunDetail;
let logViewer;
let queueManager;

document.addEventListener('DOMContentLoaded', () => {
    app = new App();
    app.init();

    // Make components globally accessible for onclick handlers
    testRunsTable = app.testRunsTable;
    testRunDetail = app.testRunDetail;
    logViewer = app.logViewer;
    queueManager = app.queueManager;
});
