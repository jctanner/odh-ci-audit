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
