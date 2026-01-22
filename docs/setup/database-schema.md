# Database Schema

## Entity Relationship Diagram

<!-- TODO: Add ER diagram -->

## Core Tables

### pull_requests

Stores GitHub PR metadata.

```sql
CREATE TABLE pull_requests (
    pr_number INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    merged_at TIMESTAMP,
    closed_at TIMESTAMP,
    state TEXT,  -- open, closed, merged
    labels JSONB,  -- JSON array of label names
    pr_metadata JSONB,  -- Full GitHub PR object
    collected_at TIMESTAMP DEFAULT NOW()
);
```

**Relationships**: 1:N with test_runs, pr_comments

### test_runs

Stores Prow CI test execution data.

```sql
CREATE TABLE test_runs (
    id SERIAL PRIMARY KEY,
    build_id TEXT UNIQUE NOT NULL,
    pr_number INTEGER REFERENCES pull_requests(pr_number),
    job_name TEXT,  -- e.g., "pull-ci-...-e2e"
    result TEXT,  -- SUCCESS, FAILURE, ABORTED
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    duration_seconds INTEGER,
    gcs_path TEXT,
    repos JSONB,  -- Repo commit SHAs
    prowjob_metadata JSONB,  -- Full prowjob.json
    collected_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_test_runs_pr_number ON test_runs(pr_number);
CREATE INDEX idx_test_runs_build_id ON test_runs(build_id);
CREATE INDEX idx_test_runs_result ON test_runs(result);
```

**Relationships**: N:1 with pull_requests, 1:N with test_cases, 1:1 with build_logs

### test_cases

Stores individual test case results from JUnit XML.

```sql
CREATE TABLE test_cases (
    id SERIAL PRIMARY KEY,
    test_run_id INTEGER REFERENCES test_runs(id),
    test_suite TEXT,
    test_name TEXT NOT NULL,
    status TEXT NOT NULL,  -- passed, failed, skipped
    duration_seconds REAL,
    failure_message TEXT,
    failure_type TEXT,
    stacktrace TEXT,
    collected_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_test_cases_test_run_id ON test_cases(test_run_id);
CREATE INDEX idx_test_cases_status ON test_cases(status);
CREATE INDEX idx_test_cases_test_name ON test_cases(test_name);
```

**Relationships**: N:1 with test_runs

### build_logs

Stores console output from Prow builds.

```sql
CREATE TABLE build_logs (
    id SERIAL PRIMARY KEY,
    test_run_id INTEGER UNIQUE REFERENCES test_runs(id),
    log_content TEXT,
    error_lines JSONB,  -- Extracted error messages
    collected_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_build_logs_test_run_id ON build_logs(test_run_id);
```

**Relationships**: 1:1 with test_runs

### pr_comments

Stores PR comments and reviews.

```sql
CREATE TABLE pr_comments (
    id SERIAL PRIMARY KEY,
    pr_number INTEGER REFERENCES pull_requests(pr_number),
    comment_id TEXT UNIQUE,
    comment_type TEXT,  -- issue_comment, review_comment, review
    author TEXT,
    body TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    comment_metadata JSONB,
    collected_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_pr_comments_pr_number ON pr_comments(pr_number);
```

**Relationships**: N:1 with pull_requests

### failure_patterns

Stores computed failure pattern analysis.

```sql
CREATE TABLE failure_patterns (
    id SERIAL PRIMARY KEY,
    pattern_hash TEXT UNIQUE NOT NULL,
    failure_type TEXT,
    signature TEXT,
    occurrences INTEGER DEFAULT 1,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    affected_prs JSONB,  -- List of PR numbers
    example_stacktrace TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_failure_patterns_failure_type ON failure_patterns(failure_type);
```

## Worker Coordination Tables

### work_queue

Coordinates parallel workers.

```sql
CREATE TABLE work_queue (
    id SERIAL PRIMARY KEY,
    pr_number INTEGER UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, claimed, completed, failed
    worker_id TEXT,
    claimed_at TIMESTAMP,
    completed_at TIMESTAMP,
    attempt_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_work_queue_status ON work_queue(status);
CREATE INDEX idx_work_queue_pr_number ON work_queue(pr_number);
```

### collection_state

Tracks collection progress for resumability.

```sql
CREATE TABLE collection_state (
    id SERIAL PRIMARY KEY,
    collection_run_id TEXT UNIQUE NOT NULL,
    last_pr_number INTEGER,
    total_prs INTEGER,
    processed_prs INTEGER,
    failed_prs INTEGER,
    started_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

## JSONB Fields (PostgreSQL)

PostgreSQL JSONB columns support advanced querying:

```sql
-- Find PRs with "bug" label
SELECT pr_number, title
FROM pull_requests
WHERE labels @> '["bug"]'::jsonb;

-- Query prowjob metadata
SELECT build_id, prowjob_metadata->>'status'
FROM test_runs
WHERE prowjob_metadata IS NOT NULL;

-- Create GIN index for JSONB
CREATE INDEX idx_prs_labels ON pull_requests USING GIN (labels);
```

## Related

- [Architecture](architecture.md)
- [PostgreSQL Deployment](postgresql-deployment.md)
- [SQL Query Library](../code/queries.md)
