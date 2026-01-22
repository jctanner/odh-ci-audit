/**
 * Component for displaying test runs table with filters
 */
class TestRunsTable {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.filters = {};
        this.currentPage = 1;
        this.perPage = 50;
        this.sortColumn = 'started_at';
        this.sortDirection = 'desc'; // 'asc' or 'desc'
    }

    async render() {
        this.container.innerHTML = `
            <div class="filters">
                <div class="filter-row">
                    <div class="filter-group">
                        <label>Repository Owner</label>
                        <input type="text" id="filter-repo-owner" placeholder="e.g., opendatahub-io">
                    </div>
                    <div class="filter-group">
                        <label>Repository Name</label>
                        <input type="text" id="filter-repo-name" placeholder="e.g., opendatahub-operator">
                    </div>
                    <div class="filter-group">
                        <label>PR Number</label>
                        <input type="text" id="filter-pr-number" placeholder="e.g., 3048">
                    </div>
                    <div class="filter-group">
                        <label>Job Type</label>
                        <input type="text" id="filter-job-name" placeholder="e.g., e2e">
                    </div>
                    <div class="filter-group">
                        <label>Result</label>
                        <select id="filter-result">
                            <option value="">All</option>
                            <option value="SUCCESS">Success</option>
                            <option value="FAILURE">Failure</option>
                            <option value="ABORTED">Aborted</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label>&nbsp;</label>
                        <button id="apply-filters">Apply Filters</button>
                    </div>
                </div>
            </div>
            <div id="test-runs-table-container">
                <div class="loading">
                    <div class="spinner"></div>
                    <p>Loading test runs...</p>
                </div>
            </div>
        `;

        // Attach event listeners
        document.getElementById('apply-filters').addEventListener('click', () => this.applyFilters());

        // Add enter key support for inputs
        ['filter-repo-owner', 'filter-repo-name', 'filter-pr-number', 'filter-job-name'].forEach(id => {
            document.getElementById(id).addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.applyFilters();
                }
            });
        });

        // Load initial data
        await this.loadTestRuns();
    }

    applyFilters() {
        this.filters = {};
        const repoOwner = document.getElementById('filter-repo-owner').value.trim();
        const repoName = document.getElementById('filter-repo-name').value.trim();
        const prNumber = document.getElementById('filter-pr-number').value.trim();
        const jobName = document.getElementById('filter-job-name').value.trim();
        const result = document.getElementById('filter-result').value;

        if (repoOwner) this.filters.repo_owner = repoOwner;
        if (repoName) this.filters.repo_name = repoName;
        if (prNumber) this.filters.pr_number = prNumber;
        if (jobName) this.filters.job_name = jobName;
        if (result) this.filters.result = result;

        this.currentPage = 1;
        this.loadTestRuns();
    }

    sortBy(column) {
        // If clicking the same column, toggle direction
        if (this.sortColumn === column) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            // New column, default to descending
            this.sortColumn = column;
            this.sortDirection = 'desc';
        }

        // Reset to first page when sorting changes
        this.currentPage = 1;
        this.loadTestRuns();
    }

    async loadTestRuns() {
        const container = document.getElementById('test-runs-table-container');
        container.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <p>Loading test runs...</p>
            </div>
        `;

        try {
            // Add sort parameters to filters
            const filtersWithSort = {
                ...this.filters,
                sort_by: this.sortColumn,
                sort_order: this.sortDirection
            };

            const data = await api.getTestRuns(filtersWithSort, this.currentPage, this.perPage);
            this.renderTable(data);
        } catch (error) {
            container.innerHTML = `
                <div class="message message-error">
                    Error loading test runs: ${error.message}
                </div>
            `;
        }
    }

    renderTable(data) {
        const container = document.getElementById('test-runs-table-container');

        if (data.test_runs.length === 0) {
            container.innerHTML = `
                <div class="message message-info">
                    No test runs found matching the filters.
                </div>
            `;
            return;
        }

        const html = `
            <div class="data-table">
                <table>
                    <thead>
                        <tr>
                            ${this.renderSortableHeader('build_id', 'Build ID')}
                            ${this.renderSortableHeader('pr_number', 'PR')}
                            <th>Repository</th>
                            ${this.renderSortableHeader('job_name', 'Job Type')}
                            ${this.renderSortableHeader('result', 'Result')}
                            ${this.renderSortableHeader('started_at', 'Started')}
                            ${this.renderSortableHeader('duration_seconds', 'Duration')}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.test_runs.map(run => this.renderRow(run)).join('')}
                    </tbody>
                </table>
            </div>
            ${this.renderPagination(data)}
        `;

        container.innerHTML = html;
    }

    renderSortableHeader(column, label) {
        const isSorted = this.sortColumn === column;
        const direction = isSorted ? this.sortDirection : '';
        const arrow = isSorted ? (direction === 'asc' ? ' ▲' : ' ▼') : '';
        const activeClass = isSorted ? 'sorted' : '';

        return `
            <th class="sortable ${activeClass}" onclick="testRunsTable.sortBy('${column}')">
                ${label}${arrow}
            </th>
        `;
    }

    renderRow(run) {
        const statusClass = this.getStatusClass(run.result);
        const startedAt = run.started_at ? new Date(run.started_at).toLocaleString() : 'N/A';
        const duration = run.duration ? `${run.duration}s` : 'N/A';
        const repo = run.repo_owner && run.repo_name ? `${run.repo_owner}/${run.repo_name}` : 'N/A';

        return `
            <tr class="clickable" onclick="app.showTestRunDetail('${run.build_id}')">
                <td><code>${run.build_id}</code></td>
                <td>#${run.pr_number}</td>
                <td>${repo}</td>
                <td>${run.job_name || 'N/A'}</td>
                <td><span class="status-badge ${statusClass}">${run.result || 'Unknown'}</span></td>
                <td>${startedAt}</td>
                <td>${duration}</td>
            </tr>
        `;
    }

    renderPagination(data) {
        const hasPrev = data.page > 1;
        const hasNext = data.page < data.total_pages;

        return `
            <div class="pagination">
                <button ${!hasPrev ? 'disabled' : ''} onclick="testRunsTable.goToPage(1)">First</button>
                <button ${!hasPrev ? 'disabled' : ''} onclick="testRunsTable.goToPage(${data.page - 1})">Previous</button>
                <span class="current-page">Page ${data.page} of ${data.total_pages} (${data.total} total)</span>
                <button ${!hasNext ? 'disabled' : ''} onclick="testRunsTable.goToPage(${data.page + 1})">Next</button>
                <button ${!hasNext ? 'disabled' : ''} onclick="testRunsTable.goToPage(${data.total_pages})">Last</button>
            </div>
        `;
    }

    goToPage(page) {
        this.currentPage = page;
        this.loadTestRuns();
    }

    getStatusClass(status) {
        switch (status) {
            case 'SUCCESS': return 'status-success';
            case 'FAILURE': return 'status-failure';
            case 'ABORTED': return 'status-aborted';
            default: return '';
        }
    }
}
