/**
 * Component for displaying test run details
 */
class TestRunDetail {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.currentBuildId = null;
        this.currentTestRun = null;
        this.currentFilter = null; // null means 'all'
    }

    async render(buildId) {
        this.currentBuildId = buildId;
        this.currentFilter = null; // Reset filter

        this.container.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <p>Loading test run details...</p>
            </div>
        `;

        try {
            const testRun = await api.getTestRunDetail(buildId);
            this.currentTestRun = testRun;
            const testCases = await api.getTestCases(buildId);
            this.renderDetail(testRun, testCases);
        } catch (error) {
            this.container.innerHTML = `
                <div class="message message-error">
                    Error loading test run: ${error.message}
                </div>
                <button class="back-button" onclick="app.showTestRuns()">Back to Test Runs</button>
            `;
        }
    }

    async filterTestCases(status) {
        this.currentFilter = status;

        // Show loading indicator for test cases section
        const testCasesContainer = document.getElementById('test-cases-container');
        if (testCasesContainer) {
            testCasesContainer.innerHTML = `
                <div class="loading">
                    <div class="spinner"></div>
                    <p>Loading test cases...</p>
                </div>
            `;
        }

        try {
            const testCases = await api.getTestCases(this.currentBuildId, status);
            this.renderTestCasesTable(testCases);
        } catch (error) {
            if (testCasesContainer) {
                testCasesContainer.innerHTML = `
                    <div class="message message-error">
                        Error loading test cases: ${error.message}
                    </div>
                `;
            }
        }
    }

    renderTestCasesTable(testCasesData) {
        const testCasesContainer = document.getElementById('test-cases-container');
        if (!testCasesContainer) return;

        const filterLabel = this.currentFilter ? this.currentFilter.charAt(0).toUpperCase() + this.currentFilter.slice(1) : 'All';
        const count = testCasesData.test_cases.length;

        testCasesContainer.innerHTML = testCasesData.test_cases.length > 0 ? `
            <div class="data-table">
                <table>
                    <thead>
                        <tr>
                            <th>Suite</th>
                            <th>Test Name</th>
                            <th>Status</th>
                            <th>Duration</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${testCasesData.test_cases.map(tc => this.renderTestCase(tc)).join('')}
                    </tbody>
                </table>
            </div>
        ` : `<p>No ${filterLabel.toLowerCase()} test cases found.</p>`;
    }

    renderDetail(testRun, testCasesData) {
        const statusClass = this.getStatusClass(testRun.result);
        const startedAt = testRun.started_at ? new Date(testRun.started_at).toLocaleString() : 'N/A';
        const finishedAt = testRun.finished_at ? new Date(testRun.finished_at).toLocaleString() : 'N/A';
        const duration = testRun.duration ? `${testRun.duration}s` : 'N/A';

        const hasE2ELog = testRun.e2e_log_path;
        const hasBuildLog = true; // Assume build log might exist

        this.container.innerHTML = `
            <div class="detail-view">
                <button class="back-button" onclick="app.showTestRuns()">← Back to Test Runs</button>

                <div class="detail-header">
                    <h2>Test Run Details</h2>
                    <p><code>${testRun.build_id}</code></p>
                </div>

                <div class="detail-grid">
                    <div class="detail-item">
                        <label>PR Number</label>
                        <div class="value">#${testRun.pr_number}</div>
                    </div>
                    ${testRun.pull_request ? `
                        <div class="detail-item">
                            <label>Repository</label>
                            <div class="value">${testRun.pull_request.repo_owner}/${testRun.pull_request.repo_name}</div>
                        </div>
                        <div class="detail-item">
                            <label>PR Title</label>
                            <div class="value">${testRun.pull_request.title}</div>
                        </div>
                        <div class="detail-item">
                            <label>Author</label>
                            <div class="value">${testRun.pull_request.author}</div>
                        </div>
                    ` : ''}
                    <div class="detail-item">
                        <label>Job Type</label>
                        <div class="value">${testRun.job_name || 'N/A'}</div>
                    </div>
                    <div class="detail-item">
                        <label>Result</label>
                        <div class="value"><span class="status-badge ${statusClass}">${testRun.result || 'Unknown'}</span></div>
                    </div>
                    <div class="detail-item">
                        <label>Started At</label>
                        <div class="value">${startedAt}</div>
                    </div>
                    <div class="detail-item">
                        <label>Finished At</label>
                        <div class="value">${finishedAt}</div>
                    </div>
                    <div class="detail-item">
                        <label>Duration</label>
                        <div class="value">${duration}</div>
                    </div>
                </div>

                <h3>Test Statistics</h3>
                <div class="detail-grid">
                    <div class="detail-item">
                        <label>Total Tests</label>
                        <div class="value">${testRun.test_stats.total}</div>
                    </div>
                    <div class="detail-item">
                        <label>Passed</label>
                        <div class="value" style="color: #155724">${testRun.test_stats.passed}</div>
                    </div>
                    <div class="detail-item">
                        <label>Failed</label>
                        <div class="value" style="color: #721c24">${testRun.test_stats.failed}</div>
                    </div>
                    <div class="detail-item">
                        <label>Skipped</label>
                        <div class="value" style="color: #856404">${testRun.test_stats.skipped}</div>
                    </div>
                </div>

                <h3>Logs</h3>
                <div class="filter-row" style="margin-bottom: 20px;">
                    ${hasE2ELog ? `
                        <div class="filter-group">
                            <button onclick="app.showLog('${testRun.build_id}', 'e2e')">View E2E Test Log</button>
                        </div>
                    ` : ''}
                    <div class="filter-group">
                        <button onclick="app.showLog('${testRun.build_id}', 'build')">View Build Log</button>
                    </div>
                </div>

                ${testCasesData.test_cases.length > 0 || testRun.test_stats.total > 0 ? `
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <h3>Test Cases</h3>
                        <div class="filter-row" style="margin: 0;">
                            <div class="filter-group">
                                <button class="filter-button ${this.currentFilter === null ? 'active' : ''}" onclick="testRunDetail.filterTestCases(null)">
                                    All (${testRun.test_stats.total})
                                </button>
                            </div>
                            ${testRun.test_stats.failed > 0 ? `
                                <div class="filter-group">
                                    <button class="filter-button ${this.currentFilter === 'failed' ? 'active' : ''}" onclick="testRunDetail.filterTestCases('failed')" style="background: #f8d7da; color: #721c24; border-color: #f5c6cb;">
                                        Failed (${testRun.test_stats.failed})
                                    </button>
                                </div>
                            ` : ''}
                            ${testRun.test_stats.passed > 0 ? `
                                <div class="filter-group">
                                    <button class="filter-button ${this.currentFilter === 'passed' ? 'active' : ''}" onclick="testRunDetail.filterTestCases('passed')" style="background: #d4edda; color: #155724; border-color: #c3e6cb;">
                                        Passed (${testRun.test_stats.passed})
                                    </button>
                                </div>
                            ` : ''}
                            ${testRun.test_stats.skipped > 0 ? `
                                <div class="filter-group">
                                    <button class="filter-button ${this.currentFilter === 'skipped' ? 'active' : ''}" onclick="testRunDetail.filterTestCases('skipped')" style="background: #fff3cd; color: #856404; border-color: #ffeaa7;">
                                        Skipped (${testRun.test_stats.skipped})
                                    </button>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                    <div id="test-cases-container">
                        ${testCasesData.test_cases.length > 0 ? `
                            <div class="data-table">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Suite</th>
                                            <th>Test Name</th>
                                            <th>Status</th>
                                            <th>Duration</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${testCasesData.test_cases.map(tc => this.renderTestCase(tc)).join('')}
                                    </tbody>
                                </table>
                            </div>
                        ` : '<p>No test cases available.</p>'}
                    </div>
                ` : '<p>No test cases available.</p>'}
            </div>
        `;
    }

    renderTestCase(testCase) {
        const statusClass = this.getTestCaseStatusClass(testCase.status);
        const duration = testCase.duration ? `${testCase.duration.toFixed(2)}s` : 'N/A';
        const hasFailure = testCase.failure_message || testCase.stacktrace;

        return `
            <tr ${hasFailure ? 'class="clickable" onclick="testRunDetail.showTestCaseDetails(' + testCase.id + ')"' : ''}>
                <td>${testCase.test_suite}</td>
                <td>${testCase.test_name}</td>
                <td><span class="status-badge ${statusClass}">${testCase.status}</span></td>
                <td>${duration}</td>
            </tr>
            ${hasFailure ? `
                <tr id="test-case-${testCase.id}-details" style="display: none;">
                    <td colspan="4" style="background: #f8f9fa;">
                        ${testCase.failure_message ? `<p><strong>Failure:</strong> ${testCase.failure_message}</p>` : ''}
                        ${testCase.stacktrace ? `<pre style="background: #fff; padding: 10px; border-radius: 4px; overflow-x: auto;">${testCase.stacktrace}</pre>` : ''}
                    </td>
                </tr>
            ` : ''}
        `;
    }

    showTestCaseDetails(testCaseId) {
        const detailsRow = document.getElementById(`test-case-${testCaseId}-details`);
        if (detailsRow) {
            detailsRow.style.display = detailsRow.style.display === 'none' ? 'table-row' : 'none';
        }
    }

    getStatusClass(status) {
        switch (status) {
            case 'SUCCESS': return 'status-success';
            case 'FAILURE': return 'status-failure';
            case 'ABORTED': return 'status-aborted';
            default: return '';
        }
    }

    getTestCaseStatusClass(status) {
        switch (status) {
            case 'passed': return 'status-success';
            case 'failed': return 'status-failure';
            case 'skipped': return 'status-aborted';
            default: return '';
        }
    }
}
