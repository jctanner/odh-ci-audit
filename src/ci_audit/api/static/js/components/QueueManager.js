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
                <h3>Add PR to Queue</h3>
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
                        <label>PR Number</label>
                        <input type="number" id="trigger-pr-number" placeholder="e.g., 3048">
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

            messageDiv.innerHTML = `
                <div class="message message-success">
                    ${result.message}
                </div>
            `;

            // Clear form
            document.getElementById('trigger-pr-number').value = '';
            document.getElementById('trigger-force').checked = false;

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
