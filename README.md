# CI Audit System

A Python-based tool for collecting and analyzing e2e/CI test data from the opendatahub-io/opendatahub-operator repository's PR history on prow.ci.openshift.org.

## Features

- **Data Collection**: Automatically collects PR metadata from GitHub and test results from Prow/GCS
- **Comprehensive Storage**: SQLite database storing PRs, test runs, test cases, and build logs
- **Intelligent Parsing**: Extracts data from junit XML, Prow JSON metadata, and build logs
- **Incremental Collection**: Resume capability with state tracking
- **Rate Limiting**: Respects GitHub and GCS API rate limits

## Project Structure

```
ci_audit/
├── src/ci_audit/          # Main package
│   ├── collectors/        # Data collection clients
│   ├── database/          # Database models and schema
│   ├── analyzers/         # Analysis tools (future)
│   ├── queries/           # Query interface (future)
│   └── utils/             # Utilities (HTTP client, rate limiter)
├── scripts/               # Command-line scripts
│   └── collect.py         # Main collection script
├── config/                # Configuration files
│   └── config.yaml.example
├── data/                  # Database and cache (gitignored)
└── tests/                 # Unit tests
```

## Setup

### 1. Install Dependencies

```bash
cd ci_audit
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy example configuration (keep ${GITHUB_TOKEN} placeholder as-is)
cp config/config.yaml.example config/config.yaml

# Create .env file and add your GitHub token
cp .env.example .env
# Edit .env and replace with your actual token:
# GITHUB_TOKEN=ghp_your_actual_token_here
```

**Important**: The `config.yaml` file uses `${GITHUB_TOKEN}` which automatically gets replaced with the value from your `.env` file. Don't edit the config.yaml to add your token directly - just put it in `.env`.

Create a GitHub Personal Access Token at https://github.com/settings/tokens with `public_repo` scope.

### 3. Run Collection

```bash
# Collect all data from last year (as configured)
python scripts/collect.py

# Specify custom date range
python scripts/collect.py --start-date 2025-10-01 --end-date 2025-12-31

# Use custom config file
python scripts/collect.py --config path/to/config.yaml
```

## Database Schema

The system uses SQLite with the following main tables:

- **pull_requests**: GitHub PR metadata
- **test_runs**: Prow test executions (one per build_id)
- **test_cases**: Individual junit test results
- **build_logs**: Console output and error lines
- **failure_patterns**: Computed failure signatures (future)
- **collection_state**: Resume state tracking

## Data Sources

### GitHub API
- PR metadata (title, author, dates, labels, etc.)
- Commit SHAs
- PR statistics (additions, deletions, comments)

### Prow CI (via GCS)
- Test run metadata (started.json, finished.json, prowjob.json)
- Junit XML test results
- Build logs
- Located at: `gs://test-platform-results/pr-logs/pull/opendatahub-io_opendatahub-operator/{PR_NUMBER}/{JOB_NAME}/{BUILD_ID}/`

## Configuration

Edit `config/config.yaml` to customize:

- **GitHub**: Repository, token, rate limits
- **GCS**: Bucket, paths, job name
- **Collection**: Date range, workers, retry settings
- **Database**: Path, SQL echo
- **Logging**: Level, format, file

## Development

### Running Tests

```bash
pytest tests/
```

### Adding New Features

The codebase is modular:

- Add new collectors in `src/ci_audit/collectors/`
- Add analysis tools in `src/ci_audit/analyzers/`
- Add database models in `src/ci_audit/database/models.py`
- Add scripts in `scripts/`

## Troubleshooting

### GitHub Rate Limit
- Authenticated: 5000 requests/hour
- Check status: The collector logs rate limit info
- Solution: Wait for reset or use multiple tokens

### GCS Access
- Bucket is public, no authentication required
- If downloads fail, check network and GCS availability

### Database Locks
- SQLite has limited concurrency
- Use single collection process
- For concurrent access, consider PostgreSQL

## Future Enhancements

- Failure pattern detection and classification
- Statistical analysis tools
- Interactive query interface
- Report generation
- Visualization dashboards
- Parallel collection optimization

## License

This is a research/analysis tool for the opendatahub-io/opendatahub-operator project.

## Contributing

This is currently a research project. Contributions welcome via pull requests.
