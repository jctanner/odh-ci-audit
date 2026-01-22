# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based CI audit system for collecting and analyzing e2e/CI test data from the opendatahub-io/opendatahub-operator repository's PR history on prow.ci.openshift.org. The project aims to classify test failures, detect patterns, and identify root causes.

## Commands

### Development Setup
```bash
# Create virtual environment and install dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure (keep ${GITHUB_TOKEN} in config.yaml, only edit .env)
cp config/config.yaml.example config/config.yaml
cp .env.example .env
# Edit .env and add GITHUB_TOKEN=ghp_your_actual_token_here
# Do NOT edit config.yaml - the ${GITHUB_TOKEN} placeholder is automatically replaced
```

### Data Collection
```bash
# Collect data using configured date range (includes PR comments)
python scripts/collect.py

# Specify custom date range
python scripts/collect.py --start-date 2025-10-01 --end-date 2025-12-31

# Skip PR comment collection (faster, collects only test data)
python scripts/collect.py --skip-comments

# Use custom config
python scripts/collect.py --config path/to/config.yaml
```

### Testing
```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=ci_audit tests/

# Run specific test file
pytest tests/test_collectors.py
```

### Database Operations
```bash
# Access PostgreSQL database
podman exec -it ci-audit-postgres psql -U ci_audit -d ci_audit

# Common queries
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT COUNT(*) FROM pull_requests;"
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT COUNT(*) FROM test_runs;"
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT COUNT(*) FROM test_cases WHERE status='failed';"
```

## Architecture

### Data Flow
1. **GitHub API** → PR metadata (via PyGithub)
2. **GCS HTTP XML API** → Discover all job types for each PR, then fetch all builds for each job type
3. **Prow Artifacts** → Download test artifacts (started.json, finished.json, prowjob.json, junit XML, logs)
4. **Parsers** → Extract structured data from artifacts
5. **Database** → Store in PostgreSQL with SQLAlchemy ORM (JSONB for JSON fields)
6. **Analysis** → (Future) Pattern detection, classification, statistics

### Key Components

**Collectors** (`src/ci_audit/collectors/`):
- `github_collector.py`: GitHub API client for PR metadata
- `gcs_collector.py`: GCS HTTP XML API client for test artifacts (no auth required for public bucket)
- `artifact_parser.py`: Parsers for junit XML, Prow JSON metadata, build logs

**Database** (`src/ci_audit/database/`):
- `models.py`: SQLAlchemy ORM models for all tables
- Schema: PullRequest → TestRun → TestCase, plus BuildLog and FailurePattern tables

**Utils** (`src/ci_audit/utils/`):
- `http_client.py`: HTTP client with exponential backoff retry logic
- `rate_limiter.py`: Token bucket rate limiter for API calls

**Scripts** (`scripts/`):
- `collect.py`: Main orchestration script for data collection (PRs, test runs, comments)
- `collect_comments.py`: (Legacy) Standalone comment collector - use `collect.py` instead

### Database Schema

**Core Relationships**:
- PullRequest (1) → TestRun (N) - One PR can have multiple test runs
- TestRun (1) → TestCase (N) - Each run has multiple test cases
- TestRun (1) → BuildLog (1) - Each run has one build log

**Key Tables**:
- `pull_requests`: GitHub PR metadata (pr_number PK, title, author, dates, labels, etc.)
- `test_runs`: Prow executions (build_id unique, pr_number FK, result, timestamps, gcs_path)
- `test_cases`: junit results (test_suite, test_name, status, failure_message, stacktrace)
- `build_logs`: Console logs (log_content, error_lines JSON)
- `failure_patterns`: Computed analysis (pattern_hash, signature, occurrences)

### Data Sources

**GitHub**: `https://api.github.com/repos/opendatahub-io/opendatahub-operator`
- Requires: Personal Access Token with `public_repo` scope
- Rate limit: 5000 requests/hour (authenticated)

**Prow/GCS**: `gs://test-platform-results/pr-logs/pull/opendatahub-io_opendatahub-operator/{PR_NUMBER}/pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-e2e/{BUILD_ID}/`
- Public bucket, no authentication required
- Access via: `https://storage.googleapis.com/{bucket}/{path}`
- HTTP XML API for listing, direct GET for downloading

**Artifacts per build**:
- `started.json`: Timestamp, PR number, commit SHA, repos
- `finished.json`: Result (SUCCESS/FAILURE/ABORTED), passed boolean, duration
- `prowjob.json`: Full ProwJob spec and status
- `artifacts/junit*.xml`: Individual test case results from Ginkgo framework
- `build-log.txt`: Console output with errors and stack traces

## Important Patterns

### Error Handling
- All collectors use retry logic with exponential backoff
- Transient errors (5xx, network) are retried
- Permanent errors (404, parse failures) are logged and skipped
- Collection continues even if individual items fail

### Rate Limiting
- Token bucket algorithm prevents API throttling
- Configurable per-service (GitHub, GCS)
- Applied automatically in HTTP client

### Incremental Collection
- Each build tracked by unique `build_id` in database
- Skip already-collected builds
- Support for resuming interrupted collection
- State tracking in `collection_state` table

### Multiple Job Types
- Each PR has multiple Prow job types (e.g., e2e, rhoai-e2e, hypershift, bundle builds)
- Collection automatically discovers all job types per PR from GCS
- Common job types:
  - `*-opendatahub-operator-e2e`: Standard e2e tests
  - `*-opendatahub-operator-rhoai-e2e`: RHOAI e2e tests
  - `*-opendatahub-operator-e2e-hypershift`: Hypershift e2e tests
  - `*-ci-bundle-*`: Bundle validation builds
  - `*-images`: Image build jobs
  - `*-pr-image-mirror`: Image mirroring jobs
- All job types are stored in the same `test_runs` table, differentiated by `job_name` column

### PR Comment Collection
- PR comments are automatically collected as part of the main collection flow
- Includes issue comments, review comments, and reviews from GitHub
- Stored in `pr_comments` table with type differentiation
- Skip already-collected comments to avoid duplicates
- Can be disabled with `--skip-comments` flag for faster collection
- Comment collection happens after all test runs are collected for each PR

### Configuration
- YAML config with environment variable substitution
- Pattern: `${VAR_NAME}` in YAML → automatically replaced with env var value from `.env`
- Sensitive data (tokens) stored ONLY in `.env` file, never in config.yaml
- The config.yaml.example has `${GITHUB_TOKEN}` placeholder - users should NOT replace this, just copy the file as-is and put actual token in `.env`

## Test Organization

**E2E Test Suites** (from opendatahub-operator repo):
- authcontroller, dashboard, datasciencepipelines
- kserve, modelregistry, kueue, gateway
- feastoperator, mlflowoperator, llamastackoperator
- Tests use Ginkgo/Gomega framework, output junit XML

**Expected Failure Categories**:
1. Infrastructure (timeouts, network, pod issues, image pull)
2. Test flakes (race conditions, intermittent failures)
3. Code regressions (assertions, panics, nil pointers)
4. Configuration (missing config, YAML errors, permissions)
5. Dependencies (missing operators, CRDs, webhooks)
6. Environment (cluster state, resource contention)

## Development Notes

- Use SQLAlchemy ORM for all database operations
- Commit database session after each PR to enable resume
- Log at INFO level for progress, DEBUG for details
- Use tqdm for progress bars in long-running operations
- All datetime objects stored as UTC
- JSON fields used for flexible metadata storage
