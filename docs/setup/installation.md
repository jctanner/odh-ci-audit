# Installation

## Prerequisites

- podman and podman-compose installed
- Git
- GitHub Personal Access Token with `public_repo` scope

## Quick Start

See [PostgreSQL Deployment](postgresql-deployment.md) for detailed instructions.

```bash
# Clone repository
git clone <repo-url>
cd ci_audit

# Configure
cp config/config.yaml.example config/config.yaml
cp .env.example .env

# Edit .env and add credentials
echo "GITHUB_TOKEN=ghp_your_token_here" >> .env
echo "POSTGRES_PASSWORD=strong_password_here" >> .env

# Build containers
podman build -t ci-audit-app -f Containerfile .
podman build -t ci-audit-api -f Containerfile.api .

# Start PostgreSQL
podman-compose up -d postgres

# Populate work queue
podman-compose up producer

# Start workers (5 workers for parallel processing)
podman-compose up -d worker1 worker2 worker3 worker4 worker5

# Start REST API and web frontend
podman-compose up -d api
```

## Access Web Interface

Once the API is running, access the web interface at:
- **URL**: http://localhost:5000
- **Features**: Browse test runs, view logs, filter results, manage work queue

## Verification

```bash
# Check database
podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -c \
  "SELECT COUNT(*) FROM pull_requests;"

# Check API
curl http://localhost:5000/api/stats/overview

# Monitor workers
podman-compose logs -f worker1 worker2 worker3 worker4 worker5
```

## Next Steps

- [Configuration](configuration.md)
- [Database Schema](database-schema.md)
- [Local Development](local-development.md)
