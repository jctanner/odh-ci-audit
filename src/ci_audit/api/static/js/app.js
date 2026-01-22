/**
 * Main application logic
 */
class App {
    constructor() {
        this.currentTab = 'jobs';
        this.testRunsTable = null;
        this.testRunDetail = null;
        this.logViewer = null;
        this.queueManager = null;
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

        // Load initial view
        this.showTestRuns();
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

        // Load tab content
        if (tabName === 'jobs') {
            this.showTestRuns();
        } else if (tabName === 'queue') {
            this.queueManager.render();
        } else if (tabName === 'stats') {
            this.showStats();
        }
    }

    showTestRuns() {
        this.currentTab = 'jobs';
        this.testRunsTable.render();
    }

    showTestRunDetail(buildId) {
        this.currentTab = 'jobs';
        this.testRunDetail.render(buildId);
    }

    showLog(buildId, logType) {
        this.currentTab = 'jobs';
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

            container.innerHTML = `
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
        } catch (error) {
            container.innerHTML = `
                <div class="message message-error">
                    Error loading statistics: ${error.message}
                </div>
            `;
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
