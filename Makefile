.PHONY: help setup clean build-containers
.PHONY: db-start db-stop db-status db-shell db-backup db-restore
.PHONY: producer-run producer-stats producer-reset-failed
.PHONY: workers-start workers-stop workers-restart workers-logs workers-status
.PHONY: collect-local collect-pr
.PHONY: queue-watch queue-status
.PHONY: docs-serve docs-build
.PHONY: test test-coverage
.DEFAULT_GOAL := help

# Colors for output
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
RESET := \033[0m

# Configuration
COMPOSE := podman-compose
POSTGRES_CONTAINER := ci-audit-postgres
DB_USER := ci_audit
DB_NAME := ci_audit
DATE_TODAY := $(shell date +%Y-%m-%d)
DATE_TOMORROW := $(shell date -d 'tomorrow' +%Y-%m-%d)
DATE_WEEK_AGO := $(shell date -d '7 days ago' +%Y-%m-%d)

##@ Help

help: ## Display this help message
	@echo "$(CYAN)CI Audit Makefile$(RESET)"
	@echo ""
	@echo "$(GREEN)Usage:$(RESET) make [target]"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  $(CYAN)%-25s$(RESET) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(RESET)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup & Installation

setup: ## Initial setup - create venv and install dependencies (local mode)
	@echo "$(GREEN)Setting up local development environment...$(RESET)"
	python3 -m venv venv
	. venv/bin/activate && pip install -r requirements.txt
	@echo "$(GREEN)✓ Setup complete. Activate with: source venv/bin/activate$(RESET)"

config: ## Create config.yaml and .env from examples
	@if [ ! -f config/config.yaml ]; then \
		echo "$(GREEN)Creating config/config.yaml from example...$(RESET)"; \
		cp config/config.yaml.example config/config.yaml; \
	else \
		echo "$(YELLOW)config/config.yaml already exists$(RESET)"; \
	fi
	@if [ ! -f .env ]; then \
		echo "$(GREEN)Creating .env from example...$(RESET)"; \
		cp .env.example .env; \
		echo "$(YELLOW)⚠ Remember to edit .env and add your GITHUB_TOKEN$(RESET)"; \
	else \
		echo "$(YELLOW).env already exists$(RESET)"; \
	fi

build-containers: ## Build podman containers for workers and producer
	@echo "$(GREEN)Building CI audit containers...$(RESET)"
	podman build -t ci-audit-app -f Containerfile .
	@echo "$(GREEN)✓ Containers built$(RESET)"

build-migration: ## Build migration container
	@echo "$(GREEN)Building migration container...$(RESET)"
	podman build -t ci-audit-migration -f Containerfile.migration .
	@echo "$(GREEN)✓ Migration container built$(RESET)"

##@ Database (PostgreSQL)

db-start: ## Start PostgreSQL database
	@echo "$(GREEN)Starting PostgreSQL database...$(RESET)"
	$(COMPOSE) up -d postgres
	@echo "$(GREEN)Waiting for database to be ready...$(RESET)"
	@sleep 5
	@podman exec $(POSTGRES_CONTAINER) pg_isready -U $(DB_USER) && \
		echo "$(GREEN)✓ PostgreSQL is ready$(RESET)" || \
		echo "$(RED)✗ PostgreSQL not ready$(RESET)"

db-stop: ## Stop PostgreSQL database
	@echo "$(YELLOW)Stopping PostgreSQL database...$(RESET)"
	$(COMPOSE) stop postgres

db-restart: ## Restart PostgreSQL database
	@echo "$(YELLOW)Restarting PostgreSQL database...$(RESET)"
	$(COMPOSE) restart postgres

db-status: ## Check database status
	@echo "$(CYAN)Database Status:$(RESET)"
	@podman ps -a --filter name=$(POSTGRES_CONTAINER) --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

db-shell: ## Open PostgreSQL shell
	@echo "$(CYAN)Opening PostgreSQL shell (use \q to exit)...$(RESET)"
	podman exec -it $(POSTGRES_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME)

db-stats: ## Show database statistics
	@echo "$(CYAN)Database Statistics:$(RESET)"
	@podman exec $(POSTGRES_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -c \
		"SELECT '  PRs: ' || COUNT(*) FROM pull_requests UNION ALL \
		 SELECT '  Test Runs: ' || COUNT(*) FROM test_runs UNION ALL \
		 SELECT '  Test Cases: ' || COUNT(*) FROM test_cases UNION ALL \
		 SELECT '  Comments: ' || COUNT(*) FROM pr_comments;"

db-backup: ## Backup PostgreSQL database to data/backup-YYYYMMDD.dump
	@echo "$(GREEN)Backing up database...$(RESET)"
	@mkdir -p data
	podman exec $(POSTGRES_CONTAINER) pg_dump -U $(DB_USER) -Fc $(DB_NAME) > data/backup-$(shell date +%Y%m%d-%H%M%S).dump
	@echo "$(GREEN)✓ Backup saved to data/backup-$(shell date +%Y%m%d-%H%M%S).dump$(RESET)"

db-restore: ## Restore database from backup (requires BACKUP_FILE=/path/to/backup.dump)
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "$(RED)Error: Specify backup file with BACKUP_FILE=/path/to/backup.dump$(RESET)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Restoring database from $(BACKUP_FILE)...$(RESET)"
	cat $(BACKUP_FILE) | podman exec -i $(POSTGRES_CONTAINER) pg_restore -U $(DB_USER) -d $(DB_NAME)
	@echo "$(GREEN)✓ Database restored$(RESET)"

db-migrate: ## Migrate SQLite to PostgreSQL (requires SQLite database at data/ci_audit.db)
	@if [ ! -f data/ci_audit.db ]; then \
		echo "$(RED)Error: SQLite database not found at data/ci_audit.db$(RESET)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Running migration from SQLite to PostgreSQL...$(RESET)"
	$(COMPOSE) --profile migration up migration
	@echo "$(GREEN)✓ Migration complete$(RESET)"

##@ Producer (Work Queue Population)

producer-run: ## Run producer to populate work queue (uses config date range)
	@echo "$(GREEN)Running producer to populate work queue...$(RESET)"
	@# Run producer in worker container to avoid restarting services
	@if podman ps --filter name=ci-audit-worker1 --format "{{.Names}}" | grep -q worker1; then \
		podman exec ci-audit-worker1 python3 scripts/producer.py; \
		echo "$(GREEN)✓ Producer complete$(RESET)"; \
	else \
		echo "$(YELLOW)Worker not running, using podman-compose...$(RESET)"; \
		$(COMPOSE) --profile setup run --rm producer; \
		echo "$(GREEN)✓ Producer complete$(RESET)"; \
		echo "$(YELLOW)Ensuring workers are running...$(RESET)"; \
		$(COMPOSE) up -d worker1 worker2 worker3 worker4 worker5; \
		echo "$(GREEN)✓ Workers restarted$(RESET)"; \
	fi

producer-today: ## Run producer for today's PRs only
	@echo "$(GREEN)Running producer for PRs created today ($(DATE_TODAY))...$(RESET)"
	@# Run producer in worker container to avoid restarting services
	@if podman ps --filter name=ci-audit-worker1 --format "{{.Names}}" | grep -q worker1; then \
		podman exec ci-audit-worker1 python3 scripts/producer.py \
			--start-date $(DATE_TODAY) --end-date $(DATE_TOMORROW); \
		echo "$(GREEN)✓ Producer complete$(RESET)"; \
	else \
		echo "$(YELLOW)Worker not running, using podman-compose...$(RESET)"; \
		$(COMPOSE) --profile setup run --rm producer python3 scripts/producer.py \
			--start-date $(DATE_TODAY) --end-date $(DATE_TOMORROW); \
		echo "$(GREEN)✓ Producer complete$(RESET)"; \
		echo "$(YELLOW)Ensuring workers are running...$(RESET)"; \
		$(COMPOSE) up -d worker1 worker2 worker3 worker4 worker5; \
		echo "$(GREEN)✓ Workers restarted$(RESET)"; \
	fi

producer-week: ## Run producer for last 7 days
	@echo "$(GREEN)Running producer for last 7 days ($(DATE_WEEK_AGO) to $(DATE_TODAY))...$(RESET)"
	@# Run producer in worker container to avoid restarting services
	@if podman ps --filter name=ci-audit-worker1 --format "{{.Names}}" | grep -q worker1; then \
		podman exec ci-audit-worker1 python3 scripts/producer.py \
			--start-date $(DATE_WEEK_AGO) --end-date $(DATE_TOMORROW); \
		echo "$(GREEN)✓ Producer complete$(RESET)"; \
	else \
		echo "$(YELLOW)Worker not running, using podman-compose...$(RESET)"; \
		$(COMPOSE) --profile setup run --rm producer python3 scripts/producer.py \
			--start-date $(DATE_WEEK_AGO) --end-date $(DATE_TOMORROW); \
		echo "$(GREEN)✓ Producer complete$(RESET)"; \
		echo "$(YELLOW)Ensuring workers are running...$(RESET)"; \
		$(COMPOSE) up -d worker1 worker2 worker3 worker4 worker5; \
		echo "$(GREEN)✓ Workers restarted$(RESET)"; \
	fi

producer-pr: ## Run producer for specific PR (requires PR=3048)
	@if [ -z "$(PR)" ]; then \
		echo "$(RED)Error: Specify PR number with PR=3048$(RESET)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Fetching PR $(PR) metadata and adding to queue...$(RESET)"
	@# Run producer in worker container to avoid restarting services
	@if podman ps --filter name=ci-audit-worker1 --format "{{.Names}}" | grep -q worker1; then \
		podman exec ci-audit-worker1 python3 scripts/producer.py \
			--start-date $(DATE_TODAY) --end-date $(DATE_TOMORROW); \
		echo "$(GREEN)✓ PR $(PR) queued (if created today)$(RESET)"; \
	else \
		echo "$(YELLOW)Worker not running, using podman-compose...$(RESET)"; \
		$(COMPOSE) --profile setup run --rm producer python3 scripts/producer.py \
			--start-date $(DATE_TODAY) --end-date $(DATE_TOMORROW); \
		echo "$(GREEN)✓ PR $(PR) queued (if created today)$(RESET)"; \
		echo "$(YELLOW)Ensuring workers are running...$(RESET)"; \
		$(COMPOSE) up -d worker1 worker2 worker3 worker4 worker5; \
		echo "$(GREEN)✓ Workers restarted$(RESET)"; \
	fi
	@echo "$(YELLOW)Note: If PR was created on a different date, use: make producer-custom START=YYYY-MM-DD END=YYYY-MM-DD$(RESET)"

producer-custom: ## Run producer for custom date range (requires START=YYYY-MM-DD END=YYYY-MM-DD)
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "$(RED)Error: Specify date range with START=2026-01-01 END=2026-01-12$(RESET)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Running producer for custom date range ($(START) to $(END))...$(RESET)"
	@# Run producer in worker container to avoid restarting services
	@if podman ps --filter name=ci-audit-worker1 --format "{{.Names}}" | grep -q worker1; then \
		podman exec ci-audit-worker1 python3 scripts/producer.py \
			--start-date $(START) --end-date $(END); \
		echo "$(GREEN)✓ Producer complete$(RESET)"; \
	else \
		echo "$(YELLOW)Worker not running, using podman-compose...$(RESET)"; \
		$(COMPOSE) --profile setup run --rm producer python3 scripts/producer.py \
			--start-date $(START) --end-date $(END); \
		echo "$(GREEN)✓ Producer complete$(RESET)"; \
		echo "$(YELLOW)Ensuring workers are running...$(RESET)"; \
		$(COMPOSE) up -d worker1 worker2 worker3 worker4 worker5; \
		echo "$(GREEN)✓ Workers restarted$(RESET)"; \
	fi

producer-stats: ## Show producer/queue statistics
	@echo "$(CYAN)Producer/Queue Statistics:$(RESET)"
	@if podman ps --filter name=ci-audit-worker1 --format "{{.Names}}" | grep -q worker1; then \
		podman exec ci-audit-worker1 python3 scripts/producer.py --stats; \
	else \
		$(COMPOSE) --profile setup run --rm producer python3 scripts/producer.py --stats; \
	fi

producer-reset-failed: ## Reset failed queue items to pending for retry
	@echo "$(YELLOW)Resetting failed queue items to pending...$(RESET)"
	@if podman ps --filter name=ci-audit-worker1 --format "{{.Names}}" | grep -q worker1; then \
		podman exec ci-audit-worker1 python3 scripts/producer.py --reset-failed; \
		echo "$(GREEN)✓ Failed items reset to pending$(RESET)"; \
	else \
		$(COMPOSE) --profile setup run --rm producer python3 scripts/producer.py --reset-failed; \
		echo "$(GREEN)✓ Failed items reset to pending$(RESET)"; \
	fi

##@ Workers (Data Collection)

workers-start: ## Start all 5 workers
	@echo "$(GREEN)Starting all workers...$(RESET)"
	$(COMPOSE) up -d worker1 worker2 worker3 worker4 worker5
	@echo "$(GREEN)✓ Workers started$(RESET)"

workers-stop: ## Stop all workers
	@echo "$(YELLOW)Stopping all workers...$(RESET)"
	$(COMPOSE) stop worker1 worker2 worker3 worker4 worker5
	@echo "$(GREEN)✓ Workers stopped$(RESET)"

workers-restart: ## Restart all workers
	@echo "$(YELLOW)Restarting all workers...$(RESET)"
	$(COMPOSE) restart worker1 worker2 worker3 worker4 worker5
	@echo "$(GREEN)✓ Workers restarted$(RESET)"

workers-logs: ## Show logs for all workers (follow mode)
	@echo "$(CYAN)Showing worker logs (Ctrl+C to exit)...$(RESET)"
	$(COMPOSE) logs -f worker1 worker2 worker3 worker4 worker5

workers-logs-recent: ## Show last 50 lines from all workers
	@echo "$(CYAN)Recent worker logs:$(RESET)"
	$(COMPOSE) logs --tail=50 worker1 worker2 worker3 worker4 worker5

workers-status: ## Show worker status
	@echo "$(CYAN)Worker Status:$(RESET)"
	@podman ps --filter name=ci-audit-worker --format "table {{.Names}}\t{{.Status}}\t{{.RunningFor}}"
	@echo ""
	@echo "$(CYAN)Active Work Claims:$(RESET)"
	@podman exec $(POSTGRES_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -t -c \
		"SELECT '  ' || worker_id || ': PR #' || STRING_AGG(pr_number::text, ', #' ORDER BY pr_number) \
		 FROM work_queue WHERE status = 'claimed' GROUP BY worker_id ORDER BY worker_id;" \
		2>/dev/null || echo "  (no active claims)"

worker-start: ## Start specific worker (requires WORKER=worker1)
	@if [ -z "$(WORKER)" ]; then \
		echo "$(RED)Error: Specify worker with WORKER=worker1$(RESET)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Starting $(WORKER)...$(RESET)"
	$(COMPOSE) up -d $(WORKER)

worker-stop: ## Stop specific worker (requires WORKER=worker1)
	@if [ -z "$(WORKER)" ]; then \
		echo "$(RED)Error: Specify worker with WORKER=worker1$(RESET)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Stopping $(WORKER)...$(RESET)"
	$(COMPOSE) stop $(WORKER)

worker-logs: ## Show logs for specific worker (requires WORKER=worker1)
	@if [ -z "$(WORKER)" ]; then \
		echo "$(RED)Error: Specify worker with WORKER=worker1$(RESET)"; \
		exit 1; \
	fi
	@echo "$(CYAN)Showing logs for $(WORKER) (Ctrl+C to exit)...$(RESET)"
	$(COMPOSE) logs -f $(WORKER)

##@ Work Queue Management

queue-watch: ## Watch queue status in real-time (uses scripts/watch-queue.sh)
	@echo "$(CYAN)Starting queue monitor (Ctrl+C to exit)...$(RESET)"
	./scripts/watch-queue.sh

queue-status: ## Show current queue status (one-time)
	@echo "$(CYAN)Work Queue Status:$(RESET)"
	@podman exec $(POSTGRES_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -t -c \
		"SELECT status || ': ' || COUNT(*) || '  (' || ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) || '%)' \
		 FROM work_queue GROUP BY status ORDER BY CASE status \
		 WHEN 'pending' THEN 1 WHEN 'claimed' THEN 2 WHEN 'completed' THEN 3 WHEN 'failed' THEN 4 END;"

queue-pending: ## Show pending queue items
	@echo "$(CYAN)Pending Queue Items:$(RESET)"
	@podman exec $(POSTGRES_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -c \
		"SELECT pr_number, attempt_count, added_at FROM work_queue WHERE status = 'pending' ORDER BY pr_number LIMIT 20;"

queue-failed: ## Show failed queue items
	@echo "$(CYAN)Failed Queue Items:$(RESET)"
	@podman exec $(POSTGRES_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -c \
		"SELECT pr_number, attempt_count, error_message, last_attempt FROM work_queue WHERE status = 'failed' ORDER BY pr_number;"

queue-claimed: ## Show currently claimed queue items
	@echo "$(CYAN)Claimed Queue Items:$(RESET)"
	@podman exec $(POSTGRES_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -c \
		"SELECT pr_number, worker_id, claimed_at FROM work_queue WHERE status = 'claimed' ORDER BY worker_id, pr_number;"

##@ Local Collection (SQLite mode)

collect-local: ## Run local collection using SQLite (uses config date range)
	@echo "$(GREEN)Running local collection with SQLite...$(RESET)"
	@if [ ! -d venv ]; then \
		echo "$(RED)Virtual environment not found. Run: make setup$(RESET)"; \
		exit 1; \
	fi
	. venv/bin/activate && python scripts/collect.py
	@echo "$(GREEN)✓ Collection complete$(RESET)"

collect-pr: ## Collect specific PR locally (requires PR=3048)
	@if [ -z "$(PR)" ]; then \
		echo "$(RED)Error: Specify PR number with PR=3048$(RESET)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Collecting PR $(PR) locally...$(RESET)"
	@if [ ! -d venv ]; then \
		echo "$(RED)Virtual environment not found. Run: make setup$(RESET)"; \
		exit 1; \
	fi
	. venv/bin/activate && python scripts/collect.py --pr-number $(PR)
	@echo "$(GREEN)✓ Collection complete for PR $(PR)$(RESET)"

##@ Documentation

docs-serve: ## Serve documentation locally (http://localhost:8000)
	@echo "$(GREEN)Starting MkDocs server at http://localhost:8000 ...$(RESET)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(RESET)"
	mkdocs serve

docs-build: ## Build documentation static site
	@echo "$(GREEN)Building documentation site...$(RESET)"
	mkdocs build
	@echo "$(GREEN)✓ Site built in site/$(RESET)"

docs-deploy: ## Build and deploy docs to tannerjc.net
	@echo "$(GREEN)Building documentation to /tmp/odh_ci_audit...$(RESET)"
	mkdocs build -d /tmp/odh_ci_audit
	@echo "$(GREEN)Deploying to tannerjc.net...$(RESET)"
	rsync -avz /tmp/odh_ci_audit tannerjc@tannerjc.net:/home/tannerjc/tannerjc.net/public/docs/.
	@echo "$(GREEN)✓ Docs deployed to https://tannerjc.net/docs/odh_ci_audit$(RESET)"

##@ Testing

test: ## Run all tests
	@echo "$(GREEN)Running tests...$(RESET)"
	@if [ ! -d venv ]; then \
		echo "$(RED)Virtual environment not found. Run: make setup$(RESET)"; \
		exit 1; \
	fi
	. venv/bin/activate && pytest tests/

test-coverage: ## Run tests with coverage report
	@echo "$(GREEN)Running tests with coverage...$(RESET)"
	@if [ ! -d venv ]; then \
		echo "$(RED)Virtual environment not found. Run: make setup$(RESET)"; \
		exit 1; \
	fi
	. venv/bin/activate && pytest --cov=ci_audit --cov-report=html tests/
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/index.html$(RESET)"

##@ Cleanup

clean: ## Clean up temporary files and caches
	@echo "$(YELLOW)Cleaning up temporary files...$(RESET)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage
	@echo "$(GREEN)✓ Cleanup complete$(RESET)"

clean-cache: ## Clean GCS artifact cache
	@echo "$(YELLOW)Cleaning GCS artifact cache...$(RESET)"
	rm -rf data/cache/*
	@echo "$(GREEN)✓ Cache cleaned$(RESET)"

clean-db: ## WARNING: Delete PostgreSQL database volume (destroys all data)
	@echo "$(RED)⚠ WARNING: This will DELETE ALL data in the PostgreSQL database!$(RESET)"
	@echo "$(YELLOW)Press Ctrl+C to cancel, or Enter to continue...$(RESET)"
	@read confirm
	@echo "$(RED)Stopping containers and removing database volume...$(RESET)"
	$(COMPOSE) down -v
	rm -rf pg_data/
	@echo "$(GREEN)✓ Database volume deleted$(RESET)"

clean-all: clean clean-cache ## Clean everything (temp files + cache)

##@ All-in-One Commands

start-all: db-start workers-start ## Start database + all workers
	@echo "$(GREEN)✓ All services started$(RESET)"

stop-all: workers-stop db-stop ## Stop all workers + database
	@echo "$(GREEN)✓ All services stopped$(RESET)"

restart-all: stop-all start-all ## Restart everything
	@echo "$(GREEN)✓ All services restarted$(RESET)"

status: db-status workers-status queue-status db-stats ## Show status of everything
	@echo ""
	@echo "$(GREEN)✓ Status check complete$(RESET)"

fresh-start: clean-db db-start producer-run workers-start ## WARNING: Fresh start (deletes DB, repopulates, starts workers)
	@echo "$(GREEN)✓ Fresh start complete$(RESET)"
	@echo "$(CYAN)Workers are now processing the queue. Watch with: make queue-watch$(RESET)"
