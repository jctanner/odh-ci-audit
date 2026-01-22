# PostgreSQL Deployment

## Overview

The CI Audit system uses PostgreSQL for all data storage and operations, providing:

- **JSONB support**: Efficient JSON querying for labels, metadata, prowjob specs
- **Parallel workers**: Atomic work coordination with `SELECT FOR UPDATE SKIP LOCKED`
- **Scalability**: Production-ready for large datasets (21K+ test runs, 1M+ test cases)
- **Advanced queries**: JSONB operators for filtering by labels, metadata
- **REST API**: Flask-based API for web interface

## Prerequisites

- podman and podman-compose installed
- GitHub Personal Access Token in .env file

## Initial Setup

```bash
# 1. Configure for PostgreSQL
cp config/config.yaml.example config/config.yaml
cp .env.example .env

# 2. Edit .env
cat >> .env <<EOF
GITHUB_TOKEN=ghp_your_token_here
POSTGRES_PASSWORD=strong_password_here
EOF

# 3. Build containers
podman build -t ci-audit-app -f Containerfile .
podman build -t ci-audit-api -f Containerfile.api .
```

## Starting Data Collection

```bash
# 1. Start PostgreSQL
podman-compose up -d postgres

# 2. Populate work queue from GitHub
podman-compose up producer

# 3. Start workers (5 workers for parallel processing)
podman-compose up -d worker1 worker2 worker3 worker4 worker5

# 4. Start REST API and web frontend
podman-compose up -d api
```

## Database Operations

### Access Database

```bash
# Interactive psql
podman exec -it ci-audit-postgres psql -U ci_audit -d ci_audit

# Single query
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT COUNT(*) FROM pull_requests;"
```

### Common Queries

```bash
# Count records
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT COUNT(*) FROM test_runs;"

# JSONB query - PRs with specific label
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT pr_number, title FROM pull_requests WHERE labels @> '[\"bug\"]'::jsonb;"

# Query prowjob metadata
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT build_id, prowjob_metadata->>'status' FROM test_runs WHERE prowjob_metadata IS NOT NULL LIMIT 5;"
```

## REST API Access

Once the API service is running, access the web interface:

```bash
# Access web interface
http://localhost:5000

# Test API endpoint
curl http://localhost:5000/api/stats/overview

# View API logs
podman-compose logs -f api
```

**Features**:
- Browse test runs with filtering (PR, repo, job type)
- View test case details and failure messages
- Read e2e logs and build logs
- Manage work queue (trigger collection, reset failed items)

## Work Queue Management

### View Queue Statistics

```bash
podman-compose run --rm producer python3 scripts/producer.py --stats
```

### Populate Queue

```bash
# Default date range from config
podman-compose up producer

# Custom date range
podman-compose run --rm producer python3 scripts/producer.py \
  --start-date 2025-07-01 --end-date 2026-01-10
```

### Reset Failed Items

```bash
# Retry failed PRs
podman-compose run --rm producer python3 scripts/producer.py --reset-failed
```

### Monitor Queue

```bash
# Real-time monitoring
watch -n 5 "podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -t -c \
  'SELECT status, COUNT(*) FROM work_queue GROUP BY status;'"
```

## Worker Management

### Start Workers

```bash
# Start all workers (5 workers for optimal parallel processing)
podman-compose up -d worker1 worker2 worker3 worker4 worker5

# Start subset for testing
podman-compose up -d worker1 worker2
```

### View Logs

```bash
# Specific worker
podman-compose logs -f worker1

# All workers
podman-compose logs -f worker1 worker2 worker3 worker4 worker5

# Tail last 20 lines
podman-compose logs -f --tail=20
```

### Manage Workers

```bash
# Stop all workers
podman-compose stop worker1 worker2 worker3 worker4 worker5

# Restart single worker
podman-compose restart worker1

# Check health (should show 5 containers when all running)
podman ps | grep ci-audit-worker
```

## Monitoring

### Database Size

```bash
# Total database size
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT pg_size_pretty(pg_database_size('ci_audit'));"

# Table sizes
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size \
   FROM pg_tables WHERE schemaname='public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"
```

### Worker Progress

```bash
# Work queue status
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT status, COUNT(*) as count,
          ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as pct
   FROM work_queue GROUP BY status;"

# Worker activity
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT worker_id, COUNT(*) as claimed
   FROM work_queue WHERE status='claimed' GROUP BY worker_id;"
```

## Maintenance

### Backup

```bash
# Dump database
podman exec ci-audit-postgres pg_dump -U ci_audit -Fc ci_audit > backup.dump

# Restore from backup
podman exec -i ci-audit-postgres pg_restore -U ci_audit -d ci_audit < backup.dump
```

### Vacuum

```bash
# Reclaim space and update statistics
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c "VACUUM ANALYZE;"
```

### Reset Everything

```bash
# WARNING: Destroys all data
podman-compose down -v
rm -rf pg_data/
```

## Troubleshooting

### PostgreSQL Won't Start

```bash
# Check logs
podman-compose logs postgres

# Check if port is in use
ss -tlnp | grep 5432
```

### Workers Not Processing

```bash
# Check worker logs
podman-compose logs worker1

# Check queue for stale claims
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT * FROM work_queue WHERE status='claimed' AND claimed_at < NOW() - INTERVAL '1 hour';"

# Reset stale claims
podman-compose run --rm producer python3 scripts/producer.py --reset-failed
```

### API Not Responding

```bash
# Check API logs
podman-compose logs api

# Restart API service
podman-compose restart api

# Verify database connection
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c "SELECT 1;"
```

## Related

- [Worker System](worker-system.md)
- [Database Schema](database-schema.md)
- [Configuration](configuration.md)
