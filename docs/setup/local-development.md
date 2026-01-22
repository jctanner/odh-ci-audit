# Local Development

## Development Environment

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .
pip install -r requirements.txt
pip install -r requirements-dev.txt  # If exists
```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=ci_audit tests/

# Run specific test file
pytest tests/test_collectors.py -v

# Run specific test
pytest tests/test_collectors.py::test_github_collector -v
```

## Database Operations

### PostgreSQL (via podman-compose)

```bash
# Access database
podman exec -it ci-audit-postgres psql -U ci_audit -d ci_audit

# Common queries
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT COUNT(*) FROM pull_requests;"

podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT * FROM test_runs LIMIT 5;"

# Export to CSV
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "COPY (SELECT * FROM test_cases WHERE status='failed') TO STDOUT WITH CSV HEADER;" > failed_tests.csv
```

### Reset Database

```bash
# Backup first
podman exec ci-audit-postgres pg_dump -U ci_audit -Fc ci_audit > backup.dump

# Stop and remove PostgreSQL container
podman-compose down postgres

# Remove persistent data
rm -rf pg_data/

# Restart PostgreSQL (creates fresh database)
podman-compose up -d postgres

# Re-populate work queue
podman-compose up producer
```

## Data Collection

### Worker-Based Collection

```bash
# Populate work queue (custom date range)
podman-compose run --rm producer python3 scripts/producer.py \
  --start-date 2025-11-01 --end-date 2025-11-30

# View queue statistics
podman-compose run --rm producer python3 scripts/producer.py --stats

# Start workers
podman-compose up -d worker1 worker2 worker3 worker4 worker5

# Monitor worker logs
podman-compose logs -f worker1

# Monitor all workers
podman-compose logs -f worker1 worker2 worker3 worker4 worker5
```

### Debugging Collection

```bash
# Run single worker in foreground for debugging
podman-compose run --rm producer python3 scripts/worker.py --poll-interval 5

# Check work queue status
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT status, COUNT(*) FROM work_queue GROUP BY status;"

# Reset failed items for retry
podman-compose run --rm producer python3 scripts/producer.py --reset-failed
```

## Code Style

<!-- TODO: Add linting/formatting requirements -->

```bash
# Format code (if using black)
black src/ tests/

# Lint code (if using flake8)
flake8 src/ tests/

# Type checking (if using mypy)
mypy src/
```

## IDE Setup

<!-- TODO: Add VSCode/PyCharm configuration -->

## Related

- [Installation](installation.md)
- [Configuration](configuration.md)
- [Database Schema](database-schema.md)
