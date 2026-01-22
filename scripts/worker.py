#!/usr/bin/env python3
"""Parallel worker for collecting CI audit data from work queue."""

import sys
import signal
import logging
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from sqlalchemy.orm import Session

from ci_audit.config import Config
from ci_audit.database.models import create_database, get_session
from ci_audit.collectors.github_collector import GitHubCollector
from ci_audit.collectors.gcs_collector import GCSCollector
from ci_audit.collectors.artifact_parser import (
    JunitParser, ProwMetadataParser, BuildLogParser
)
from ci_audit.utils.http_client import RetryHTTPClient
from ci_audit.utils.rate_limiter import RateLimiter
from ci_audit.workers.queue_manager import QueueManager


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


class Worker:
    """Parallel worker for processing PRs from work queue."""

    def __init__(self, config: Config, worker_id: str, collect_comments: bool = True):
        """Initialize worker.

        Args:
            config: Configuration object
            worker_id: Unique worker identifier
            collect_comments: Whether to collect PR comments
        """
        self.config = config
        self.worker_id = worker_id
        self.collect_comments = collect_comments

        # Initialize database
        logger.info(f"Worker {worker_id}: Connecting to database...")
        self.engine = create_database(
            config.database_url,
            echo=config.get('database.echo_sql', False)
        )

        # Initialize GitHub collector
        logger.info(f"Worker {worker_id}: Initializing GitHub collector...")
        self.github_collector = GitHubCollector(
            token=config.github_token,
            repo_owner=config.github_repo_owner,
            repo_name=config.github_repo_name
        )

        # Initialize GCS collector
        logger.info(f"Worker {worker_id}: Initializing GCS collector...")
        gcs_rate_limiter = RateLimiter(
            requests_per_second=config.get('gcs.rate_limit_requests', 1000) / config.get('gcs.rate_limit_period', 60)
        )
        http_client = RetryHTTPClient(
            max_retries=config.get('collection.retry_attempts', 3),
            backoff_factor=config.get('collection.retry_backoff', 2),
            rate_limiter=gcs_rate_limiter
        )
        self.gcs_collector = GCSCollector(http_client=http_client)

        # Initialize parsers
        self.junit_parser = JunitParser()
        self.metadata_parser = ProwMetadataParser()
        self.log_parser = BuildLogParser()

        logger.info(f"Worker {worker_id}: Initialization complete")

    def run(self, poll_interval: int = 5, no_work_log_interval: int = 60):
        """Run worker loop.

        Args:
            poll_interval: Seconds to sleep when no work available
            no_work_log_interval: Seconds between "No work available" log messages
        """
        logger.info(f"Worker {self.worker_id}: Starting worker loop (poll_interval={poll_interval}s)")

        consecutive_failures = 0
        max_consecutive_failures = 5
        last_no_work_log_time = 0  # Track when we last logged "no work available"

        while not shutdown_requested:
            session = get_session(self.engine)

            try:
                # Initialize queue manager
                queue_mgr = QueueManager(
                    session=session,
                    worker_id=self.worker_id,
                    claim_timeout_minutes=self.config.get('workers.claim_timeout_minutes', 30),
                    max_retries=self.config.get('workers.max_retries', 3)
                )

                # Try to claim work
                work = queue_mgr.claim_work()

                if work:
                    # Work available - process PR
                    repo_owner = work['repo_owner']
                    repo_name = work['repo_name']
                    pr_number = work['pr_number']

                    try:
                        logger.info(f"Worker {self.worker_id}: Processing {repo_owner}/{repo_name}#{pr_number}")

                        # Get PR object from GitHub
                        pr = self.github_collector.repo.get_pull(pr_number)

                        # Collect all data for this PR
                        self._collect_pr_data(session, pr, repo_owner, repo_name)

                        # Mark as completed
                        queue_mgr.mark_completed(repo_owner, repo_name, pr_number)

                        # Reset failure counter on success
                        consecutive_failures = 0

                    except Exception as e:
                        logger.error(f"Worker {self.worker_id}: Failed to process {repo_owner}/{repo_name}#{pr_number}: {e}")
                        queue_mgr.mark_failed(repo_owner, repo_name, pr_number, str(e))
                        consecutive_failures += 1

                        # If too many consecutive failures, back off
                        if consecutive_failures >= max_consecutive_failures:
                            logger.warning(
                                f"Worker {self.worker_id}: {consecutive_failures} consecutive failures, "
                                f"backing off for {poll_interval * 5}s"
                            )
                            time.sleep(poll_interval * 5)
                            consecutive_failures = 0

                else:
                    # No work available - log stats (throttled) and sleep
                    current_time = time.time()
                    if current_time - last_no_work_log_time >= no_work_log_interval:
                        stats = queue_mgr.get_queue_stats()
                        logger.info(
                            f"Worker {self.worker_id}: No work available. "
                            f"Queue: {stats['pending']} pending, {stats['claimed']} claimed, "
                            f"{stats['completed']} completed, {stats['failed']} failed"
                        )
                        last_no_work_log_time = current_time
                    time.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Worker {self.worker_id}: Unexpected error in worker loop: {e}")
                consecutive_failures += 1
                time.sleep(poll_interval)

            finally:
                session.close()

        logger.info(f"Worker {self.worker_id}: Shutdown complete")

    def _collect_pr_data(self, session: Session, pr, repo_owner: str, repo_name: str):
        """Collect all data for a single PR.

        This is adapted from DataCollector.collect_pr_data() but works
        within the worker's existing session.

        Args:
            session: Database session
            pr: GitHub PullRequest object
            repo_owner: Repository owner
            repo_name: Repository name
        """
        from ci_audit.database.models import (
            PullRequest, TestRun, TestCase, BuildLog, PRComment
        )
        from datetime import datetime, timezone
        import json

        try:
            # Store PR metadata
            pr_metadata = self.github_collector.get_pr_metadata(pr)

            # Check if PR already exists for this repo
            db_pr = session.query(PullRequest).filter_by(
                repo_owner=repo_owner,
                repo_name=repo_name,
                pr_number=pr_metadata['pr_number']
            ).first()

            if db_pr:
                # Update existing PR
                db_pr.repo_owner = repo_owner
                db_pr.repo_name = repo_name
                for key, value in pr_metadata.items():
                    if key == 'labels':
                        setattr(db_pr, key, json.dumps(value))
                    elif key == 'metadata':
                        setattr(db_pr, 'pr_metadata', json.dumps(value))
                    elif key != 'pr_number':
                        setattr(db_pr, key, value)
                db_pr.last_collected_at = datetime.now(timezone.utc)
            else:
                # Create new PR
                db_pr = PullRequest(
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    pr_number=pr_metadata['pr_number'],
                    title=pr_metadata['title'],
                    author=pr_metadata['author'],
                    state=pr_metadata['state'],
                    created_at=pr_metadata['created_at'],
                    updated_at=pr_metadata['updated_at'],
                    merged_at=pr_metadata['merged_at'],
                    closed_at=pr_metadata['closed_at'],
                    base_ref=pr_metadata['base_ref'],
                    head_ref=pr_metadata['head_ref'],
                    head_sha=pr_metadata['head_sha'],
                    labels=json.dumps(pr_metadata['labels']),
                    is_draft=pr_metadata['is_draft'],
                    pr_metadata=json.dumps(pr_metadata['metadata']),
                    last_collected_at=datetime.now(timezone.utc)
                )
                session.add(db_pr)

            session.flush()

            # Track collection stats
            total_builds_found = 0
            total_builds_cached = 0
            total_builds_downloaded = 0

            # Discover all job types for this PR
            job_names = self.gcs_collector.list_job_names(
                bucket=self.config.gcs_bucket,
                base_path=self.config.gcs_base_path,
                pr_number=pr.number
            )

            if not job_names:
                logger.warning(f"Worker {self.worker_id}: No job types found for PR #{pr.number}")
                session.commit()
                return

            # Process each job type
            for job_name in job_names:
                # Get build IDs for this job type
                build_ids = self.gcs_collector.list_build_ids(
                    bucket=self.config.gcs_bucket,
                    base_path=self.config.gcs_base_path,
                    pr_number=pr.number,
                    job_name=job_name
                )

                if not build_ids:
                    logger.debug(f"No builds found for job {job_name}")
                    continue

                # Check which builds are already collected
                cached_count = 0
                new_builds = []
                refetched_count = 0
                for build_id in build_ids:
                    existing = session.query(TestRun).filter_by(build_id=build_id).first()
                    if existing:
                        # Check if build is incomplete/aborted and needs refetching
                        is_incomplete = (
                            existing.finished_at is None or
                            existing.result is None or
                            existing.result in ['ABORTED', 'PENDING']
                        )

                        if is_incomplete:
                            logger.info(
                                f"Worker {self.worker_id}: PR #{pr.number} build {build_id}: "
                                f"Incomplete/aborted (result={existing.result}), re-collecting..."
                            )
                            # Delete incomplete build (cascade deletes test_cases and build_log)
                            session.delete(existing)
                            session.flush()  # Ensure deletion is committed before re-collection
                            new_builds.append(build_id)
                            refetched_count += 1
                        else:
                            cached_count += 1
                    else:
                        new_builds.append(build_id)

                # Update totals
                total_builds_found += len(build_ids)
                total_builds_cached += cached_count

                # Extract short job name for logging
                job_short = job_name.split('-')[-1] if '-' in job_name else job_name

                # Log summary for this job type
                if new_builds:
                    new_count = len(new_builds) - refetched_count
                    status_parts = [f"{cached_count} cached"]
                    if refetched_count > 0:
                        status_parts.append(f"{refetched_count} refetched")
                    if new_count > 0:
                        status_parts.append(f"{new_count} new")

                    logger.info(
                        f"Worker {self.worker_id}: PR #{pr.number} [{job_short}]: "
                        f"Found {len(build_ids)} build(s) ({', '.join(status_parts)}) - downloading..."
                    )
                else:
                    logger.info(
                        f"Worker {self.worker_id}: PR #{pr.number} [{job_short}]: "
                        f"Found {len(build_ids)} build(s) (all cached, skipping)"
                    )

                # Process new builds
                downloaded = 0
                for idx, build_id in enumerate(new_builds, 1):
                    try:
                        logger.info(
                            f"Worker {self.worker_id}: PR #{pr.number} [{job_short}]: "
                            f"Downloading build {idx}/{len(new_builds)} ({build_id})"
                        )
                        self._collect_build_data(session, db_pr.id, pr.number, build_id, job_name)
                        downloaded += 1
                    except Exception as e:
                        logger.error(
                            f"Worker {self.worker_id}: Failed to collect build {build_id} "
                            f"for PR #{pr.number}: {e}"
                        )
                        continue

                total_builds_downloaded += downloaded

            # Collect PR comments (if enabled)
            if self.collect_comments:
                try:
                    self._collect_pr_comments(session, pr, db_pr.id, pr.number)
                except Exception as e:
                    logger.error(
                        f"Worker {self.worker_id}: Failed to collect comments "
                        f"for PR #{pr.number}: {e}"
                    )
                    # Continue even if comment collection fails

            # Log summary for this PR
            if total_builds_found > 0:
                logger.info(
                    f"Worker {self.worker_id}: PR #{pr.number} COMPLETE: "
                    f"{total_builds_found} total build(s), "
                    f"{total_builds_cached} cached, "
                    f"{total_builds_downloaded} downloaded"
                )
            else:
                logger.info(f"Worker {self.worker_id}: PR #{pr.number} COMPLETE: No builds found")

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Worker {self.worker_id}: Failed to process PR #{pr.number}: {e}")
            raise

    def _collect_build_data(self, session: Session, pr_id: int, pr_number: int, build_id: str, job_name: str):
        """Collect and store data for a single build.

        Args:
            session: Database session
            pr_id: Pull request database ID (synthetic PK)
            pr_number: Pull request number (for GCS path)
            build_id: Build ID
            job_name: Prow job name
        """
        from ci_audit.database.models import TestRun, TestCase, BuildLog
        import json

        logger.debug(f"Collecting build {build_id} for PR #{pr_number} job {job_name}")

        # Download all artifacts
        artifacts = self.gcs_collector.get_build_artifacts(
            bucket=self.config.gcs_bucket,
            base_path=self.config.gcs_base_path,
            pr_number=pr_number,
            job_name=job_name,
            build_id=build_id
        )

        # Parse metadata
        started_data = None
        finished_data = None
        prowjob_data = None

        if artifacts.get('started.json'):
            started_data = self.metadata_parser.parse_started(artifacts['started.json'])

        if artifacts.get('finished.json'):
            finished_data = self.metadata_parser.parse_finished(artifacts['finished.json'])

        if artifacts.get('prowjob.json'):
            prowjob_data = self.metadata_parser.parse_prowjob(artifacts['prowjob.json'])

        # Create TestRun record
        gcs_path = f"{self.config.gcs_base_path}/{pr_number}/{job_name}/{build_id}"

        test_run = TestRun(
            build_id=build_id,
            pr_id=pr_id,
            pr_number=pr_number,
            job_name=job_name,
            started_at=started_data['timestamp'] if started_data else None,
            finished_at=finished_data['timestamp'] if finished_data else None,
            duration_seconds=(finished_data['timestamp'] - started_data['timestamp']).total_seconds() if (started_data and finished_data) else None,
            result=finished_data['result'] if finished_data else None,
            passed=finished_data['passed'] if finished_data else None,
            commit_sha=finished_data.get('revision') if finished_data else None,
            gcs_path=gcs_path,
            repos=json.dumps(started_data.get('repos', {})) if started_data else None,
            node_name=started_data.get('node_name') if started_data else None,
            prowjob_metadata=json.dumps(prowjob_data) if prowjob_data else None,
        )
        session.add(test_run)
        session.flush()

        # Download e2e test execution log to filesystem (if this is an e2e job)
        if any(job_type in job_name for job_type in ['e2e', 'rhoai-e2e']):
            try:
                # Construct filesystem path: /logs/{org}_{repo}/pr-{pr_number}/{build_id}/{job_type}-build-log.txt
                org_repo = f"{self.config.github_repo_owner}_{self.config.github_repo_name}"
                job_short = job_name.split('-')[-1] if '-' in job_name else job_name
                log_filename = f"{job_short}-build-log.txt"
                e2e_log_path = Path(f"/logs/{org_repo}/pr-{pr_number}/{build_id}/{log_filename}")

                # Download log from GCS to filesystem
                success = self.gcs_collector.download_e2e_log(
                    bucket=self.config.gcs_bucket,
                    base_path=self.config.gcs_base_path,
                    pr_number=pr_number,
                    job_name=job_name,
                    build_id=build_id,
                    output_path=e2e_log_path
                )

                if success:
                    # Store path in database
                    test_run.e2e_log_path = str(e2e_log_path)
                    logger.debug(f"E2E log saved to {e2e_log_path}")
                else:
                    logger.debug(f"No e2e log found for build {build_id}")

            except Exception as e:
                logger.warning(f"Failed to download e2e log for build {build_id}: {e}")
                # Don't fail the entire build collection if log download fails

        # Parse and store junit test cases
        for artifact_name, content in artifacts.items():
            if artifact_name.startswith('junit:') and content:
                test_cases = self.junit_parser.parse(content)

                for tc in test_cases:
                    test_case = TestCase(
                        run_id=test_run.id,
                        test_suite=tc['test_suite'],
                        test_name=tc['test_name'],
                        classname=tc['classname'],
                        status=tc['status'],
                        duration_seconds=tc['duration_seconds'],
                        failure_message=tc['failure_message'],
                        failure_type=tc['failure_type'],
                        failure_stacktrace=tc['failure_stacktrace'],
                        system_out=tc['system_out'],
                        system_err=tc['system_err'],
                    )
                    session.add(test_case)

        # Parse and store build log
        if artifacts.get('build-log.txt'):
            log_data = self.log_parser.parse(artifacts['build-log.txt'])

            build_log = BuildLog(
                run_id=test_run.id,
                log_content=log_data['log_content'],
                log_size_bytes=log_data['log_size_bytes'],
                error_lines=json.dumps(log_data['error_lines']),
            )
            session.add(build_log)

        session.flush()
        logger.debug(f"Successfully collected build {build_id}")

    def _collect_pr_comments(self, session: Session, pr, pr_id: int, pr_number: int):
        """Collect and store comments for a PR.

        Args:
            session: Database session
            pr: GitHub PullRequest object
            pr_id: Pull request database ID (synthetic PK)
            pr_number: Pull request number
        """
        from ci_audit.database.models import PRComment
        import json

        # Check if comments already exist
        existing_count = session.query(PRComment).filter_by(pr_number=pr_number).count()
        if existing_count > 0:
            logger.info(
                f"Worker {self.worker_id}: PR #{pr_number}: "
                f"{existing_count} comment(s) already cached, skipping"
            )
            return

        # Get all comments
        logger.info(f"Worker {self.worker_id}: PR #{pr_number}: Fetching comments from GitHub...")
        comments = self.github_collector.get_all_pr_comments(pr)

        if not comments:
            logger.info(f"Worker {self.worker_id}: PR #{pr_number}: No comments found")
            return

        # Count comment types
        comment_types = {}
        for comment_data in comments:
            ctype = comment_data['comment_type']
            comment_types[ctype] = comment_types.get(ctype, 0) + 1

        # Store comments in database
        stored_count = 0
        for comment_data in comments:
            # Check if comment already exists
            existing = session.query(PRComment).filter_by(
                comment_id=comment_data['comment_id']
            ).first()

            if existing:
                continue

            # Create new comment
            comment = PRComment(
                pr_id=pr_id,
                pr_number=pr_number,
                comment_id=comment_data['comment_id'],
                comment_type=comment_data['comment_type'],
                author=comment_data['author'],
                created_at=comment_data['created_at'],
                updated_at=comment_data.get('updated_at'),
                body=comment_data.get('body'),
                review_state=comment_data.get('review_state'),
                in_reply_to_id=comment_data.get('in_reply_to_id'),
                path=comment_data.get('path'),
                line=comment_data.get('line'),
                commit_id=comment_data.get('commit_id'),
                comment_metadata=json.dumps(comment_data.get('metadata', {}))
            )
            session.add(comment)
            stored_count += 1

        if stored_count > 0:
            session.flush()
            type_summary = ", ".join([f"{count} {ctype}" for ctype, count in comment_types.items()])
            logger.info(
                f"Worker {self.worker_id}: PR #{pr_number}: "
                f"Stored {stored_count} comment(s) ({type_summary})"
            )


@click.command()
@click.option('--config', default='config/config.yaml', help='Path to configuration file')
@click.option('--worker-id', help='Worker ID (defaults to hostname or WORKER_ID env var)')
@click.option('--poll-interval', default=5, type=int, help='Seconds to sleep when no work available')
@click.option('--no-work-log-interval', default=60, type=int, help='Seconds between "no work available" log messages')
@click.option('--skip-comments', is_flag=True, help='Skip collecting PR comments')
def main(config, worker_id, poll_interval, no_work_log_interval, skip_comments):
    """Run parallel worker for CI audit data collection."""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Load configuration
    cfg = Config(config)

    # Determine worker ID
    if not worker_id:
        worker_id = cfg.worker_id

    logger.info(f"Starting worker: {worker_id}")
    logger.info(f"Configuration loaded from {config}")
    logger.info(f"Database: {cfg.database_url.split('@')[-1] if '@' in cfg.database_url else cfg.database_url}")
    if skip_comments:
        logger.info("Comment collection disabled (--skip-comments)")

    # Create and run worker
    worker = Worker(cfg, worker_id, collect_comments=not skip_comments)
    worker.run(poll_interval=poll_interval, no_work_log_interval=no_work_log_interval)


if __name__ == '__main__':
    main()
