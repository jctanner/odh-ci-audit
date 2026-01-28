/**
 * Component for managing the work queue
 */
class QueueManager {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
    }

    async render() {
        this.container.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <p>Loading queue statistics...</p>
            </div>
        `;

        try {
            const stats = await api.getQueueStats();
            const overallStats = await api.getStats();
            this.renderQueue(stats, overallStats);
        } catch (error) {
            this.container.innerHTML = `
                <div class="message message-error">
                    Error loading queue: ${error.message}
                </div>
            `;
        }
    }

    renderQueue(stats, overallStats) {
        this.container.innerHTML = `
            <h2>Queue Statistics</h2>
            <div class="queue-stats">
                <div class="stat-card">
                    <div class="number">${stats.pending || 0}</div>
                    <div class="label">Pending</div>
                </div>
                <div class="stat-card">
                    <div class="number">${stats.claimed || 0}</div>
                    <div class="label">In Progress</div>
                </div>
                <div class="stat-card">
                    <div class="number">${stats.completed || 0}</div>
                    <div class="label">Completed</div>
                </div>
                <div class="stat-card">
                    <div class="number">${stats.failed || 0}</div>
                    <div class="label">Failed</div>
                </div>
                <div class="stat-card">
                    <div class="number">${stats.total || 0}</div>
                    <div class="label">Total Items</div>
                </div>
            </div>

            <h2 style="margin-top: 40px;">Overall Statistics</h2>
            <div class="queue-stats">
                <div class="stat-card">
                    <div class="number">${overallStats.test_runs.total}</div>
                    <div class="label">Total Test Runs</div>
                </div>
                <div class="stat-card">
                    <div class="number">${overallStats.test_runs.pass_rate}%</div>
                    <div class="label">Pass Rate</div>
                </div>
                <div class="stat-card">
                    <div class="number">${overallStats.pull_requests.total}</div>
                    <div class="label">Total PRs</div>
                </div>
                <div class="stat-card">
                    <div class="number">${overallStats.test_cases.total}</div>
                    <div class="label">Total Test Cases</div>
                </div>
            </div>

            <h2 style="margin-top: 40px;">Trigger Collection</h2>
            <div class="trigger-form">
                <h3>Add PR(s) to Queue</h3>
                <div class="form-row">
                    <div class="form-group">
                        <label>Repository Owner</label>
                        <input type="text" id="trigger-repo-owner" placeholder="e.g., opendatahub-io" value="opendatahub-io">
                    </div>
                    <div class="form-group">
                        <label>Repository Name</label>
                        <input type="text" id="trigger-repo-name" placeholder="e.g., opendatahub-operator" value="opendatahub-operator">
                    </div>
                    <div class="form-group">
                        <label>PR Number(s)</label>
                        <input type="text" id="trigger-pr-number" placeholder="e.g., 3048 or 3048,3049,3050">
                    </div>
                </div>
                <div class="checkbox-group" style="margin-bottom: 15px;">
                    <input type="checkbox" id="trigger-force">
                    <label for="trigger-force">Force re-collection (even if already completed)</label>
                </div>
                <button class="submit-button" onclick="queueManager.triggerCollection()">Add to Queue</button>
            </div>

            <div class="trigger-form" style="margin-top: 20px;">
                <h3>Collect New PRs from GitHub</h3>
                <p>Fetch recent PRs from GitHub (from last collected PR to today) and add them to the queue.</p>
                <button class="submit-button" onclick="queueManager.collectNewPRs()">Collect New PRs</button>
            </div>

            <div class="trigger-form" style="margin-top: 20px;">
                <h3>Validate PR Collection</h3>
                <p>Check if we have the latest test runs for a PR by comparing with GCS.</p>
                <div class="form-row">
                    <div class="form-group">
                        <label>Repository Owner</label>
                        <input type="text" id="validate-repo-owner" placeholder="e.g., opendatahub-io" value="opendatahub-io">
                    </div>
                    <div class="form-group">
                        <label>Repository Name</label>
                        <input type="text" id="validate-repo-name" placeholder="e.g., opendatahub-operator" value="opendatahub-operator">
                    </div>
                    <div class="form-group">
                        <label>PR Number</label>
                        <input type="number" id="validate-pr-number" placeholder="e.g., 3048">
                    </div>
                </div>
                <button class="submit-button" onclick="queueManager.validatePR()">Validate PR</button>
                <div id="validation-results" style="margin-top: 20px;"></div>
            </div>

            ${stats.failed > 0 ? `
                <div class="trigger-form" style="margin-top: 20px;">
                    <h3>Reset Failed Items</h3>
                    <p>Reset all failed items to pending status for retry.</p>
                    <button class="submit-button danger-button" onclick="queueManager.resetFailed()">Reset ${stats.failed} Failed Item${stats.failed !== 1 ? 's' : ''}</button>
                </div>
            ` : ''}

            ${stats.completed > 0 ? `
                <div class="trigger-form" style="margin-top: 20px;">
                    <h3>Re-Collect All PRs</h3>
                    <p>Reset all completed items to pending for re-collection. This will refetch incomplete/aborted builds while skipping successfully completed builds.</p>
                    <button class="submit-button danger-button" onclick="queueManager.resetCompleted()">Re-Collect ${stats.completed} Completed Item${stats.completed !== 1 ? 's' : ''}</button>
                </div>
            ` : ''}

            ${stats.recent_activity && stats.recent_activity.length > 0 ? `
                <h2 style="margin-top: 40px;">Recent Activity</h2>
                <div class="data-table">
                    <table>
                        <thead>
                            <tr>
                                <th>PR</th>
                                <th>Repository</th>
                                <th>Status</th>
                                <th>Worker</th>
                                <th>Updated</th>
                                <th>Attempts</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${stats.recent_activity.map(item => this.renderActivityRow(item)).join('')}
                        </tbody>
                    </table>
                </div>
            ` : ''}

            <div id="queue-message"></div>
        `;
    }

    renderActivityRow(item) {
        const statusClass = this.getStatusClass(item.status);
        const updatedAt = item.updated_at ? new Date(item.updated_at).toLocaleString() : 'N/A';
        const repo = `${item.repo_owner}/${item.repo_name}`;

        return `
            <tr>
                <td>#${item.pr_number}</td>
                <td>${repo}</td>
                <td><span class="status-badge ${statusClass}">${item.status}</span></td>
                <td>${item.worker_id || 'N/A'}</td>
                <td>${updatedAt}</td>
                <td>${item.attempt_count}</td>
            </tr>
        `;
    }

    async triggerCollection() {
        const repoOwner = document.getElementById('trigger-repo-owner').value.trim();
        const repoName = document.getElementById('trigger-repo-name').value.trim();
        const prNumber = document.getElementById('trigger-pr-number').value.trim();
        const force = document.getElementById('trigger-force').checked;

        const messageDiv = document.getElementById('queue-message');

        // Validate inputs
        if (!repoOwner || !repoName || !prNumber) {
            messageDiv.innerHTML = `
                <div class="message message-error">
                    Please fill in all fields.
                </div>
            `;
            return;
        }

        try {
            const result = await api.triggerCollection(prNumber, repoOwner, repoName, force);

            // Build summary message
            let summaryMessage = `<strong>Total: ${result.total} PR(s)</strong><br>`;
            if (result.created > 0) summaryMessage += `✓ Created: ${result.created}<br>`;
            if (result.reset > 0) summaryMessage += `↻ Reset: ${result.reset}<br>`;
            if (result.skipped > 0) summaryMessage += `⊘ Skipped: ${result.skipped}<br>`;

            // Build detailed results table if multiple PRs
            let detailsTable = '';
            if (result.results && result.results.length > 1) {
                detailsTable = `
                    <div style="margin-top: 15px;">
                        <strong>Details:</strong>
                        <table style="width: 100%; margin-top: 10px; font-size: 0.9em;">
                            <thead>
                                <tr>
                                    <th style="text-align: left; padding: 5px;">PR</th>
                                    <th style="text-align: left; padding: 5px;">Status</th>
                                    <th style="text-align: left; padding: 5px;">Message</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${result.results.map(r => `
                                    <tr>
                                        <td style="padding: 5px;">#${r.pr_number}</td>
                                        <td style="padding: 5px;">${r.status}</td>
                                        <td style="padding: 5px; font-size: 0.85em;">${r.message}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            }

            messageDiv.innerHTML = `
                <div class="message message-success">
                    ${summaryMessage}
                    ${detailsTable}
                </div>
            `;

            // Clear only the PR number field (keep repo owner/name for convenience)
            document.getElementById('trigger-pr-number').value = '';

            // Reload queue stats after a short delay
            setTimeout(() => this.render(), 1000);
        } catch (error) {
            messageDiv.innerHTML = `
                <div class="message message-error">
                    Error: ${error.message}
                </div>
            `;
        }
    }

    async resetFailed() {
        const messageDiv = document.getElementById('queue-message');

        if (!confirm('Are you sure you want to reset all failed items to pending?')) {
            return;
        }

        try {
            const result = await api.resetFailed();

            messageDiv.innerHTML = `
                <div class="message message-success">
                    ${result.message}
                </div>
            `;

            // Reload queue stats
            setTimeout(() => this.render(), 1000);
        } catch (error) {
            messageDiv.innerHTML = `
                <div class="message message-error">
                    Error: ${error.message}
                </div>
            `;
        }
    }

    async resetCompleted() {
        const messageDiv = document.getElementById('queue-message');

        if (!confirm('Are you sure you want to reset all completed items to pending for re-collection?\n\nThis will re-collect all PRs and refetch any incomplete/aborted builds.')) {
            return;
        }

        try {
            const result = await api.resetCompleted();

            messageDiv.innerHTML = `
                <div class="message message-success">
                    ${result.message}
                </div>
            `;

            // Reload queue stats
            setTimeout(() => this.render(), 1000);
        } catch (error) {
            messageDiv.innerHTML = `
                <div class="message message-error">
                    Error: ${error.message}
                </div>
            `;
        }
    }

    async collectNewPRs() {
        const messageDiv = document.getElementById('queue-message');

        messageDiv.innerHTML = `
            <div class="message message-info">
                Fetching new PRs from GitHub... This may take a moment.
            </div>
        `;

        try {
            const result = await api.collectNewPRs();

            if (result.status === 'error') {
                messageDiv.innerHTML = `
                    <div class="message message-error">
                        ${result.message}
                    </div>
                `;
                return;
            }

            const prList = result.pr_numbers && result.pr_numbers.length > 0
                ? `<br><strong>PR numbers:</strong> ${result.pr_numbers.join(', ')}`
                : '';

            messageDiv.innerHTML = `
                <div class="message message-success">
                    ${result.message}${prList}
                </div>
            `;

            // Reload queue stats
            setTimeout(() => this.render(), 1000);
        } catch (error) {
            messageDiv.innerHTML = `
                <div class="message message-error">
                    Error: ${error.message}
                </div>
            `;
        }
    }

    async validatePR() {
        const repoOwner = document.getElementById('validate-repo-owner').value.trim();
        const repoName = document.getElementById('validate-repo-name').value.trim();
        const prNumber = document.getElementById('validate-pr-number').value.trim();
        const resultsDiv = document.getElementById('validation-results');

        // Validate input
        if (!repoOwner || !repoName || !prNumber) {
            resultsDiv.innerHTML = `
                <div class="message message-error">
                    Please fill in all fields.
                </div>
            `;
            return;
        }

        resultsDiv.innerHTML = `
            <div class="message message-info">
                Validating ${repoOwner}/${repoName} PR #${prNumber}... This may take a moment.
            </div>
        `;

        try {
            const result = await api.validatePR(prNumber, repoOwner, repoName);

            if (result.status === 'error') {
                resultsDiv.innerHTML = `
                    <div class="message message-error">
                        ${result.message}
                    </div>
                `;
                return;
            }

            if (result.status === 'not_found') {
                resultsDiv.innerHTML = `
                    <div class="message message-warning">
                        ${result.message}
                    </div>
                `;
                return;
            }

            // Display validation results
            const statusClass = result.is_current ? 'message-success' : 'message-warning';
            const statusIcon = result.is_current ? '✓' : '⚠';

            let jobsTable = '';
            if (result.jobs && result.jobs.length > 0) {
                jobsTable = `
                    <div class="data-table" style="margin-top: 15px;">
                        <table>
                            <thead>
                                <tr>
                                    <th>Job Name</th>
                                    <th>DB Build</th>
                                    <th>GCS Build</th>
                                    <th>Status</th>
                                    <th>DB Runs</th>
                                    <th>GCS Builds</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${result.jobs.map(job => this.renderValidationJobRow(job)).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            }

            resultsDiv.innerHTML = `
                <div class="message ${statusClass}">
                    <strong>${statusIcon} ${result.message}</strong><br>
                    <small>
                        ${result.current_job_types} of ${result.total_job_types} job types are current
                    </small>
                </div>
                ${jobsTable}
            `;
        } catch (error) {
            resultsDiv.innerHTML = `
                <div class="message message-error">
                    Error: ${error.message}
                </div>
            `;
        }
    }

    renderValidationJobRow(job) {
        const statusClass = job.is_current ? 'status-success' : 'status-warning';
        const statusText = job.is_current ? 'Current' : 'Outdated';
        const dbBuild = job.db_latest_build || 'N/A';
        const gcsBuild = job.gcs_latest_build || 'N/A';

        return `
            <tr>
                <td>${job.job_name}</td>
                <td>${dbBuild}</td>
                <td>${gcsBuild}</td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>${job.db_total_runs || 0}</td>
                <td>${job.gcs_total_builds || 0}</td>
            </tr>
        `;
    }

    getStatusClass(status) {
        switch (status) {
            case 'pending': return 'status-pending';
            case 'claimed': return 'status-claimed';
            case 'completed': return 'status-completed';
            case 'failed': return 'status-failed';
            default: return '';
        }
    }
}
