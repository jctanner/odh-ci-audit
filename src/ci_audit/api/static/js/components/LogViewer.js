/**
 * Component for viewing logs
 */
class LogViewer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.currentBuildId = null;
        this.currentLogType = null;
    }

    async render(buildId, logType) {
        this.currentBuildId = buildId;
        this.currentLogType = logType;

        const logTitle = logType === 'e2e' ? 'E2E Test Log' : 'Build Log';

        this.container.innerHTML = `
            <div class="detail-view">
                <button class="back-button" onclick="app.showTestRunDetail('${buildId}')">← Back to Test Run</button>

                <div class="detail-header">
                    <h2>${logTitle}</h2>
                    <p><code>${buildId}</code></p>
                </div>

                <div class="loading">
                    <div class="spinner"></div>
                    <p>Loading log...</p>
                </div>
            </div>
        `;

        try {
            let logContent;
            if (logType === 'e2e') {
                logContent = await api.getE2ELog(buildId);
            } else {
                logContent = await api.getBuildLog(buildId);
            }

            this.renderLog(logContent, logTitle, buildId);
        } catch (error) {
            this.container.innerHTML = `
                <div class="detail-view">
                    <button class="back-button" onclick="app.showTestRunDetail('${buildId}')">← Back to Test Run</button>

                    <div class="detail-header">
                        <h2>${logTitle}</h2>
                        <p><code>${buildId}</code></p>
                    </div>

                    <div class="message message-error">
                        Error loading log: ${error.message}
                    </div>
                </div>
            `;
        }
    }

    renderLog(content, title, buildId) {
        // Escape HTML to prevent XSS
        const escaped = this.escapeHtml(content);

        this.container.innerHTML = `
            <div class="detail-view">
                <button class="back-button" onclick="app.showTestRunDetail('${buildId}')">← Back to Test Run</button>

                <div class="log-header">
                    <h3>${title}</h3>
                    <button onclick="logViewer.downloadLog()">Download Log</button>
                </div>

                <div class="log-viewer">
                    <pre>${escaped}</pre>
                </div>
            </div>
        `;
    }

    downloadLog() {
        if (!this.currentBuildId || !this.currentLogType) return;

        // Create a download link
        const logType = this.currentLogType === 'e2e' ? 'e2e' : 'build';
        const filename = `${this.currentBuildId}-${logType}-log.txt`;

        const element = document.createElement('a');
        const logContent = document.querySelector('.log-viewer pre').textContent;
        const file = new Blob([logContent], { type: 'text/plain' });
        element.href = URL.createObjectURL(file);
        element.download = filename;
        document.body.appendChild(element);
        element.click();
        document.body.removeChild(element);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
