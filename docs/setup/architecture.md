# Architecture

## System Overview

<!-- TODO: Add architecture diagram -->

## Components

### Data Collection

- **GitHub Collector**: Fetches PR metadata via GitHub API
- **GCS Collector**: Downloads test artifacts from Google Cloud Storage
- **Artifact Parser**: Parses JUnit XML, Prow JSON, and build logs

### Data Storage

- **Database Models**: SQLAlchemy ORM models
- **PostgreSQL**: Database with JSONB support for flexible JSON storage

### Parallel Processing

- **Producer**: Populates work queue from GitHub PRs
- **Workers**: Process PRs concurrently (5 workers default)
- **Queue Manager**: Coordinates work distribution using PostgreSQL SELECT FOR UPDATE SKIP LOCKED

### Web Interface

- **REST API**: Flask-based API for querying test data
- **Frontend**: Vanilla JavaScript single-page application
- **Features**: Browse test runs, view logs, filter by PR/repo/job type, manage work queue

### Analysis

- **SQL Queries**: Direct database queries for analysis
- **JSONB Queries**: Advanced filtering using PostgreSQL JSONB operators
- **Python Scripts**: Data processing and visualization
- **Pattern Detection**: (Planned) Automated failure classification

## Data Flow

```
GitHub API → PRs → Work Queue (PostgreSQL)
                     ↓
              Worker Pool (5x)
                     ↓
     GCS → Artifacts → Parser → PostgreSQL (JSONB)
                                    ↓
                         ┌──────────┴──────────┐
                         ↓                     ↓
                   REST API             Analysis Scripts
                         ↓
                   Web Frontend
```

## Design Decisions

### Why SQLAlchemy?

SQLAlchemy provides:
- Database abstraction while maintaining PostgreSQL-specific features (JSONB)
- Type-safe ORM models with relationships
- Connection pooling for concurrent workers
- Migration support for schema evolution

### Why PostgreSQL?

PostgreSQL is required for:
- **JSONB columns**: Store flexible JSON data (labels, metadata, prowjob specs) with indexing and querying
- **Advanced queries**: `WHERE labels @> '["bug"]'::jsonb` for filtering
- **Concurrency**: `SELECT FOR UPDATE SKIP LOCKED` for atomic work claiming by parallel workers
- **Connection pooling**: Handle 5 concurrent workers efficiently
- **Scalability**: Production-ready for large datasets (21K+ test runs, 1M+ test cases)

### Why Parallel Workers?

Performance comparison:
- **Sequential**: ~2-3 hours for 100 PRs
- **5 Workers**: ~30-45 minutes for 100 PRs (3-4x speedup)
- Work queue prevents duplicate processing
- Graceful handling of worker failures

## Related

- [Database Schema](database-schema.md)
- [Worker System](worker-system.md)
- [PostgreSQL Deployment](postgresql-deployment.md)
