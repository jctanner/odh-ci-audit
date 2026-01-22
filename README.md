# CI Audit System

A Python-based tool for collecting and analyzing e2e/CI test data from the opendatahub-io/opendatahub-operator repository's PR history on prow.ci.openshift.org.

## Features

- **Data Collection**: Automatically collects PR metadata from GitHub and test results from Prow/GCS
- **Comprehensive Storage**: PostgreSQL database storing PRs, test runs, test cases, and build logs
- **Intelligent Parsing**: Extracts data from junit XML, Prow JSON metadata, and build logs
- **Incremental Collection**: Resume capability with state tracking
- **Rate Limiting**: Respects GitHub and GCS API rate limits
- **Parallel Processing**: Multi-worker architecture for efficient data collection

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

### Prerequisites

- podman and podman-compose installed
- GitHub Personal Access Token (create at https://github.com/settings/tokens with `public_repo` scope)

### 1. Configure

```bash
# Copy example configuration (keep ${GITHUB_TOKEN} placeholder as-is)
cp config/config.yaml.example config/config.yaml

# Create .env file and add your GitHub token and database password
cp .env.example .env
# Edit .env and set:
# GITHUB_TOKEN=ghp_your_actual_token_here
# POSTGRES_PASSWORD=strong_password_here
```

**Important**: The `config.yaml` file uses `${GITHUB_TOKEN}` which automatically gets replaced with the value from your `.env` file. Don't edit the config.yaml to add your token directly - just put it in `.env`.

### 2. Build and Start Services

```bash
# Build application container
podman build -t ci-audit-app -f Containerfile .

# Start PostgreSQL
podman-compose up -d postgres

# Wait for PostgreSQL to be ready
podman exec ci-audit-postgres pg_isready -U ci_audit
```

### 3. Populate Work Queue

```bash
# Populate queue from GitHub PRs
podman-compose up producer

# Or with custom date range
podman-compose run --rm producer python3 scripts/producer.py \
  --start-date 2025-10-01 --end-date 2025-12-31
```

### 4. Start Workers

```bash
# Start all 5 workers to process the queue
podman-compose up -d worker1 worker2 worker3 worker4 worker5

# Monitor progress
podman-compose logs -f --tail=20
```

## Database Schema

The system uses PostgreSQL with the following main tables:

- **pull_requests**: GitHub PR metadata (with JSONB for labels and metadata)
- **test_runs**: Prow test executions (one per build_id, with JSONB for prowjob metadata)
- **test_cases**: Individual junit test results
- **build_logs**: Console output and error lines
- **pr_comments**: PR comments and reviews
- **failure_patterns**: Computed failure signatures (future)
- **work_queue**: Worker coordination and claim management
- **collection_state**: Resume state tracking

See [Database Schema Documentation](docs/setup/database-schema.md) for complete details.

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

Edit `config/config.yaml` and `.env` to customize:

- **GitHub**: Repository, token (in .env), rate limits
- **GCS**: Bucket, paths, job name pattern
- **Collection**: Date range, retry settings
- **Database**: PostgreSQL connection (password in .env)
- **Logging**: Level, format, file
- **Workers**: Concurrency, claim timeout

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

### Worker Management
- Monitor worker health: `podman ps | grep ci-audit-worker`
- View logs: `podman-compose logs -f worker1`
- Restart workers: `podman-compose restart worker1`
- Scale workers up/down as needed

## Future Enhancements

- Failure pattern detection and classification
- Statistical analysis tools
- Interactive query interface
- Report generation
- Visualization dashboards

## License

This is a research/analysis tool for the opendatahub-io/opendatahub-operator project.

## Contributing

This is currently a research project. Contributions welcome via pull requests.
