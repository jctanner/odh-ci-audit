# Configuration

## Configuration Files

- `config/config.yaml`: Main configuration (copy from config.yaml.example)
- `.env`: Environment variables (NEVER commit to git)

## Environment Variables

```bash
# .env file
GITHUB_TOKEN=ghp_your_personal_access_token_here
POSTGRES_PASSWORD=your_postgres_password_here
```

## config.yaml Structure

```yaml
github:
  token: ${GITHUB_TOKEN}  # Do NOT replace - reads from .env
  repo_owner: "opendatahub-io"
  repo_name: "opendatahub-operator"
  rate_limit_requests: 5000
  rate_limit_period: 3600  # 1 hour in seconds

gcs:
  bucket: "test-platform-results"
  base_path: "pr-logs/pull/opendatahub-io_opendatahub-operator"
  job_name: "pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-e2e"
  rate_limit_requests: 1000
  rate_limit_period: 60  # 1 minute in seconds

database:
  # PostgreSQL database connection
  user: ${POSTGRES_USER}
  password: ${POSTGRES_PASSWORD}
  host: ${POSTGRES_HOST}
  port: ${POSTGRES_PORT}
  name: ${POSTGRES_DB}
  pool_size: 10
  max_overflow: 20
  echo_sql: false

collection:
  start_date: "2025-07-01"
  end_date: "2026-01-10"
  max_workers: 5
  retry_attempts: 3
  retry_backoff: 2
  cache_artifacts: true
  cache_directory: ./data/cache

workers:
  enabled: true  # Parallel worker mode
  claim_timeout_minutes: 30
  max_retries: 3

analysis:
  pattern_similarity_threshold: 0.85
  min_pattern_occurrences: 3
  clustering_algorithm: dbscan

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: ./ci_audit.log
```

## Environment Variable Substitution

The system automatically replaces `${VAR_NAME}` patterns in config.yaml with values from .env:

```yaml
# config.yaml
github:
  token: ${GITHUB_TOKEN}

# .env
GITHUB_TOKEN=ghp_abc123

# Result: token = "ghp_abc123"
```

## PostgreSQL Configuration

All database credentials should be set via environment variables in `.env`:

```bash
POSTGRES_USER=ci_audit
POSTGRES_PASSWORD=strong_password_here
POSTGRES_HOST=postgres  # Container name in podman-compose
POSTGRES_PORT=5432
POSTGRES_DB=ci_audit
```

The config.yaml references these via `${VARIABLE_NAME}` placeholders.

## Worker Configuration

Parallel processing is enabled by default:

```yaml
workers:
  enabled: true
  claim_timeout_minutes: 30  # Release stale claims after this period
  max_retries: 3  # Maximum retry attempts for failed PRs
```

Run 5 workers for optimal performance without overwhelming GitHub rate limits.

## Related

- [Installation](installation.md)
- [PostgreSQL Deployment](postgresql-deployment.md)
- [Worker System](worker-system.md)
