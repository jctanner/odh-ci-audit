#!/bin/bash
# Migration script for SQLite to PostgreSQL using pgloader
set -e

echo "=================================================="
echo "CI Audit: SQLite to PostgreSQL Migration"
echo "=================================================="

# Configuration (from environment or defaults)
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-ci_audit}"
POSTGRES_DB="${POSTGRES_DB:-ci_audit}"
SQLITE_DB="${SQLITE_DB:-/migration/ci_audit.db}"
PGLOADER_CONFIG="${PGLOADER_CONFIG:-/migration/pgloader.load}"

echo ""
echo "Configuration:"
echo "  PostgreSQL: ${POSTGRES_HOST}:${POSTGRES_PORT}"
echo "  Database:   ${POSTGRES_DB}"
echo "  User:       ${POSTGRES_USER}"
echo "  SQLite DB:  ${SQLITE_DB}"
echo ""

# Check if SQLite database exists
if [ ! -f "${SQLITE_DB}" ]; then
    echo "ERROR: SQLite database not found at ${SQLITE_DB}"
    echo "Please ensure the database is mounted at /migration/ci_audit.db"
    exit 1
fi

# Get SQLite database size
SQLITE_SIZE=$(du -h "${SQLITE_DB}" | cut -f1)
echo "SQLite database size: ${SQLITE_SIZE}"
echo ""

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
MAX_ATTEMPTS=30
ATTEMPT=0

until pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ ${ATTEMPT} -ge ${MAX_ATTEMPTS} ]; then
        echo "ERROR: PostgreSQL not ready after ${MAX_ATTEMPTS} attempts"
        exit 1
    fi
    echo "  Attempt ${ATTEMPT}/${MAX_ATTEMPTS}: PostgreSQL not ready, waiting..."
    sleep 2
done

echo "PostgreSQL is ready!"
echo ""

# Check if database already has data (skip migration if so)
echo "Checking if database already contains data..."
EXISTING_ROWS=$(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';" 2>/dev/null || echo "0")

if [ "${EXISTING_ROWS}" -gt 7 ]; then
    echo "WARNING: Database already contains ${EXISTING_ROWS} tables"
    echo "Migration may have already been completed. Checking for data..."

    TEST_CASES_COUNT=$(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SELECT COUNT(*) FROM test_cases;" 2>/dev/null || echo "0")

    if [ "${TEST_CASES_COUNT}" -gt 0 ]; then
        echo "Found ${TEST_CASES_COUNT} test cases in database"
        echo "Migration appears complete. Skipping pgloader."
        echo ""
        echo "If you want to re-run migration:"
        echo "  1. Drop the database: podman exec ci-audit-postgres psql -U ci_audit -c 'DROP DATABASE ci_audit;'"
        echo "  2. Recreate: podman exec ci-audit-postgres psql -U ci_audit -c 'CREATE DATABASE ci_audit;'"
        echo "  3. Restart migration: podman-compose up migration"
        exit 0
    fi
fi

echo "Database is empty, proceeding with migration..."
echo ""

# Run pgloader
echo "=================================================="
echo "Starting pgloader migration..."
echo "=================================================="
echo ""

if [ ! -f "${PGLOADER_CONFIG}" ]; then
    echo "ERROR: pgloader configuration not found at ${PGLOADER_CONFIG}"
    exit 1
fi

# Run pgloader with verbose output
pgloader --verbose "${PGLOADER_CONFIG}"

PGLOADER_EXIT=$?

echo ""
if [ ${PGLOADER_EXIT} -ne 0 ]; then
    echo "ERROR: pgloader failed with exit code ${PGLOADER_EXIT}"
    exit ${PGLOADER_EXIT}
fi

echo "=================================================="
echo "Migration complete! Verifying data..."
echo "=================================================="
echo ""

# Verify migration by checking row counts
echo "Verifying row counts:"
psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" << EOF
SELECT
    'pull_requests' AS table_name,
    COUNT(*) AS row_count
FROM pull_requests
UNION ALL
SELECT
    'test_runs' AS table_name,
    COUNT(*) AS row_count
FROM test_runs
UNION ALL
SELECT
    'test_cases' AS table_name,
    COUNT(*) AS row_count
FROM test_cases
UNION ALL
SELECT
    'build_logs' AS table_name,
    COUNT(*) AS row_count
FROM build_logs
UNION ALL
SELECT
    'pr_comments' AS table_name,
    COUNT(*) AS row_count
FROM pr_comments
UNION ALL
SELECT
    'failure_patterns' AS table_name,
    COUNT(*) AS row_count
FROM failure_patterns
UNION ALL
SELECT
    'collection_state' AS table_name,
    COUNT(*) AS row_count
FROM collection_state
ORDER BY table_name;
EOF

echo ""
echo "=================================================="
echo "Migration Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Verify row counts match your SQLite database"
echo "  2. Start producer to populate work queue:"
echo "     podman-compose up producer"
echo "  3. Start workers:"
echo "     podman-compose up -d worker1 worker2 worker3 worker4 worker5"
echo ""
