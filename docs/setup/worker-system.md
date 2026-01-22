# Worker System

## Overview

The worker system enables parallel PR processing using PostgreSQL for coordination.

**Architecture**:

- **Producer**: Populates work queue with PR numbers from GitHub
- **Workers**: Independent processes that claim and process PRs
- **Queue Manager**: Coordinates work distribution via PostgreSQL
- **Database**: Atomic work claiming with `SELECT FOR UPDATE SKIP LOCKED`

## Components

### Producer

Fetches PRs from GitHub and populates the work queue.

```bash
# Run producer
podman-compose up producer

# Custom date range
podman-compose run --rm producer python3 scripts/producer.py \
  --start-date 2025-07-01 --end-date 2026-01-10

# View statistics
podman-compose run --rm producer python3 scripts/producer.py --stats
```

### Workers

Process PRs from the queue concurrently.

```bash
# Start workers (5 workers for optimal parallel processing)
podman-compose up -d worker1 worker2 worker3 worker4 worker5

# Each worker:
# 1. Claims PR atomically from queue
# 2. Collects test data from GCS
# 3. Parses and stores in database
# 4. Marks PR as completed or failed
```

### Queue Manager

Handles work coordination:

- **Atomic Claiming**: Uses PostgreSQL row locking
- **Stale Detection**: Releases claims after timeout
- **Retry Logic**: Failed PRs can be retried
- **Progress Tracking**: Status updates for monitoring

## Work Queue States

```
pending → claimed → completed
            ↓
          failed (can be reset to pending)
```

**State Transitions**:

- `pending`: PR in queue, not yet claimed
- `claimed`: Worker is processing
- `completed`: Successfully processed
- `failed`: Processing failed (can retry)

## Atomic Work Claiming

PostgreSQL-specific query for lock-free claiming:

```sql
-- Worker claims next pending PR
UPDATE work_queue
SET status = 'claimed',
    worker_id = 'worker1',
    claimed_at = NOW(),
    attempt_count = attempt_count + 1
WHERE id = (
    SELECT id FROM work_queue
    WHERE status = 'pending'
    ORDER BY pr_number
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING pr_number;
```

**How it works**:

- `SELECT FOR UPDATE`: Locks row during transaction
- `SKIP LOCKED`: Skip rows locked by other workers
- Atomic operation prevents duplicate work

## Stale Claim Detection

Workers periodically release stale claims:

```sql
-- Find claims older than timeout
UPDATE work_queue
SET status = 'pending',
    worker_id = NULL,
    claimed_at = NULL
WHERE status = 'claimed'
  AND claimed_at < NOW() - INTERVAL '30 minutes';
```

**Configuration**:

```yaml
# config.yaml
workers:
  claim_timeout_minutes: 30
```

## Retry Logic

Failed PRs can be retried:

```bash
# Reset all failed items to pending
podman-compose run --rm producer python3 scripts/producer.py --reset-failed

# SQL equivalent:
# UPDATE work_queue SET status='pending', worker_id=NULL WHERE status='failed';
```

**Attempt Tracking**:

```sql
-- Track retry attempts
SELECT pr_number, attempt_count, error_message
FROM work_queue
WHERE status = 'failed'
ORDER BY attempt_count DESC;
```

## Monitoring

### Queue Status

```bash
# Current status breakdown
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT status, COUNT(*) FROM work_queue GROUP BY status;"
```

### Worker Activity

```bash
# Active workers
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT worker_id, COUNT(*) as processing
   FROM work_queue WHERE status='claimed' GROUP BY worker_id;"
```

### Progress

```bash
# Completion percentage
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT
     COUNT(*) FILTER (WHERE status='completed') as completed,
     COUNT(*) FILTER (WHERE status='pending') as pending,
     COUNT(*) FILTER (WHERE status='claimed') as claimed,
     COUNT(*) FILTER (WHERE status='failed') as failed,
     ROUND(100.0 * COUNT(*) FILTER (WHERE status='completed') / COUNT(*), 2) as pct_complete
   FROM work_queue;"
```

## Performance

### Speedup

Parallel processing provides 3-4x speedup over sequential:

- **Sequential**: ~2-3 hours for 100 PRs
- **Parallel** (5 workers): ~30-45 minutes for 100 PRs

**Performance factors**:

- GCS download latency (majority of time)
- Parsing overhead (junit XML, build logs)
- Database write operations with connection pooling
- GitHub API rate limits (5000 requests/hour per token)

### Scaling

**Current Deployment**: 5 workers

```bash
# Start all workers
podman-compose up -d worker1 worker2 worker3 worker4 worker5
```

**Worker Count Considerations**:

- **CPU**: 2-4 cores per worker (parsing)
- **Network**: GCS bandwidth (no auth, public bucket)
- **Database**: PostgreSQL connection pooling (pool_size=10, max_overflow=20)
- **GitHub API rate limits**: 5000 requests/hour per token
  - 5 workers stay within rate limits for typical workload
  - Each PR: ~10-20 GitHub API calls (metadata, comments)
  - ~250-500 PRs/hour max throughput before rate limiting

**Scaling Beyond 5 Workers**:

For higher throughput, implement:
1. Per-worker GitHub token rotation
2. Distributed rate limiting coordination
3. Additional worker containers in podman-compose.yml

## Troubleshooting

### Workers Stuck

```bash
# Check for stale claims
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT pr_number, worker_id, claimed_at,
          NOW() - claimed_at as duration
   FROM work_queue
   WHERE status='claimed'
   ORDER BY claimed_at;"

# Force reset stale claims
UPDATE work_queue
SET status='pending', worker_id=NULL
WHERE status='claimed' AND claimed_at < NOW() - INTERVAL '1 hour';
```

### Worker Crashes

```bash
# Check worker logs
podman-compose logs worker1 --tail=100

# Restart crashed worker
podman-compose restart worker1

# Stale claim will be auto-released after timeout
```

### High Failure Rate

```bash
# Analyze failures
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT error_message, COUNT(*) as count
   FROM work_queue
   WHERE status='failed'
   GROUP BY error_message
   ORDER BY count DESC;"

# Common issues:
# - Network timeouts (retry)
# - Invalid PR (skip)
# - Database errors (investigate)
```

## Code Reference

- `src/ci_audit/workers/queue_manager.py`: Queue coordination logic
- `scripts/producer.py`: Queue population
- `scripts/worker.py`: Worker implementation

## Related

- [PostgreSQL Deployment](postgresql-deployment.md)
- [Database Schema](database-schema.md)
- [Configuration](configuration.md)
