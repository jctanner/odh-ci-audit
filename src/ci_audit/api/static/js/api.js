/**
 * API client for CI Audit backend
 */
class APIClient {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
    }

    async request(url, options = {}) {
        const response = await fetch(`${this.baseURL}${url}`, options);

        // For text responses (logs)
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('text/plain')) {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return await response.text();
        }

        // For JSON responses
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}: ${response.statusText}`);
        }
        return data;
    }

    async getTestRuns(filters = {}, page = 1, perPage = 50) {
        const params = new URLSearchParams({
            page: page.toString(),
            per_page: perPage.toString(),
            ...filters
        });

        return await this.request(`/api/test-runs?${params}`);
    }

    async getTestRunDetail(buildId) {
        return await this.request(`/api/test-runs/${buildId}`);
    }

    async getTestCases(buildId, statusFilter = null) {
        const params = statusFilter ? `?status=${statusFilter}` : '';
        return await this.request(`/api/test-runs/${buildId}/test-cases${params}`);
    }

    async getE2ELog(buildId) {
        return await this.request(`/api/logs/e2e/${buildId}`);
    }

    async getBuildLog(buildId) {
        return await this.request(`/api/logs/build/${buildId}`);
    }

    async getQueueStats() {
        return await this.request('/api/queue/stats');
    }

    async triggerCollection(prNumber, repoOwner, repoName, force = false) {
        return await this.request('/api/queue/trigger', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                pr_number: parseInt(prNumber),
                repo_owner: repoOwner,
                repo_name: repoName,
                force: force
            })
        });
    }

    async resetFailed() {
        return await this.request('/api/queue/reset-failed', {
            method: 'POST'
        });
    }

    async resetCompleted() {
        return await this.request('/api/queue/reset-completed', {
            method: 'POST'
        });
    }

    async collectNewPRs() {
        return await this.request('/api/queue/collect-new-prs', {
            method: 'POST'
        });
    }

    async getStats() {
        return await this.request('/api/stats/overview');
    }

    async getTimeline(days = 30) {
        return await this.request(`/api/stats/timeline?days=${days}`);
    }

    async getDuration(days = 30) {
        return await this.request(`/api/stats/duration?days=${days}`);
    }
}

// Global API client instance
const api = new APIClient();
