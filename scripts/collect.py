#!/usr/bin/env python3
"""Main collection script for CI audit data."""

import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from sqlalchemy.orm import Session
from tqdm import tqdm

from ci_audit.config import Config
from ci_audit.database.models import (
    create_database, get_session,
    PullRequest, TestRun, TestCase, BuildLog, PRComment, CollectionState
)
from ci_audit.collectors.github_collector import GitHubCollector
from ci_audit.collectors.gcs_collector import GCSCollector
from ci_audit.collectors.artifact_parser import (
    JunitParser, ProwMetadataParser, BuildLogParser
)
from ci_audit.utils.http_client import RetryHTTPClient
from ci_audit.utils.rate_limiter import RateLimiter


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataCollector:
    """Main data collection orchestrator."""

    def __init__(self, config: Config, collect_comments: bool = True):
        """Initialize collector.

        Args:
            config: Configuration object
            collect_comments: Whether to collect PR comments (default: True)
        """
        self.config = config
        self.collect_comments = collect_comments

        # Initialize database
        db_path = Path(config.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_database(f"sqlite:///{db_path}", echo=config.get('database.echo_sql', False))

        # Initialize collectors
        logger.info("Initializing GitHub collector...")
        self.github_collector = GitHubCollector(
            token=config.github_token,
            repo_owner=config.github_repo_owner,
            repo_name=config.github_repo_name
        )

        logger.info("Initializing GCS collector...")
        gcs_rate_limiter = RateLimiter(
            requests_per_second=config.get('gcs.rate_limit_requests', 1000) / config.get('gcs.rate_limit_period', 60)
        )
        http_client = RetryHTTPClient(
            max_retries=config.get('collection.retry_attempts', 3),
            backoff_factor=config.get('collection.retry_backoff', 2),
            rate_limiter=gcs_rate_limiter
        )
        self.gcs_collector = GCSCollector(http_client=http_client)

        # Parsers
        self.junit_parser = JunitParser()
        self.metadata_parser = ProwMetadataParser()
        self.log_parser = BuildLogParser()

    def collect_all(self, start_date: datetime, end_date: datetime):
        """Collect all data for the specified date range.

        Args:
            start_date: Start date for PR collection
            end_date: End date for PR collection
        """
        logger.info(f"Starting collection from {start_date} to {end_date}")

        # Get all PRs in date range
        logger.info("Fetching PRs from GitHub...")
        prs = self.github_collector.get_prs_in_date_range(start_date, end_date)
        logger.info(f"Found {len(prs)} PRs to process")

        # Process each PR
        for pr in tqdm(prs, desc="Processing PRs"):
            try:
                self.collect_pr_data(pr)
            except Exception as e:
                logger.error(f"Failed to collect data for PR #{pr.number}: {e}")
                continue

        logger.info("Collection complete!")

    def collect_pr_data(self, pr):
        """Collect all data for a single PR.

        Args:
            pr: GitHub PullRequest object
        """
        session = get_session(self.engine)

        try:
            # Store PR metadata
            pr_metadata = self.github_collector.get_pr_metadata(pr)
            db_pr = self._store_pr_metadata(session, pr_metadata)

            # Track collection stats for this PR
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
                logger.warning(f"No job types found for PR #{pr.number}")
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
                                f"PR #{pr.number} build {build_id}: "
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

                # Extract short job name for cleaner logging
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
                        f"PR #{pr.number} [{job_short}]: Found {len(build_ids)} build(s) "
                        f"({', '.join(status_parts)}) - downloading..."
                    )
                else:
                    logger.info(
                        f"PR #{pr.number} [{job_short}]: Found {len(build_ids)} build(s) "
                        f"(all cached, skipping)"
                    )

                # Process new builds
                downloaded = 0
                for idx, build_id in enumerate(new_builds, 1):
                    try:
                        logger.info(f"PR #{pr.number} [{job_short}]: Downloading build {idx}/{len(new_builds)} ({build_id})")
                        self._collect_build_data(session, pr.number, build_id, job_name)
                        downloaded += 1
                    except Exception as e:
                        logger.error(f"Failed to collect build {build_id} for PR #{pr.number}: {e}")
                        continue

                total_builds_downloaded += downloaded

            # Collect PR comments (if enabled)
            if self.collect_comments:
                try:
                    self._collect_pr_comments(session, pr, pr.number)
                except Exception as e:
                    logger.error(f"Failed to collect comments for PR #{pr.number}: {e}")
                    # Continue even if comment collection fails

            # Log summary for this PR
            if total_builds_found > 0:
                logger.info(
                    f"PR #{pr.number} COMPLETE: "
                    f"{total_builds_found} total build(s), "
                    f"{total_builds_cached} cached, "
                    f"{total_builds_downloaded} downloaded"
                )
            else:
                logger.info(f"PR #{pr.number} COMPLETE: No builds found")

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to process PR #{pr.number}: {e}")
            raise
        finally:
            session.close()

    def _store_pr_metadata(self, session: Session, pr_metadata: dict) -> PullRequest:
        """Store or update PR metadata in database.

        Args:
            session: Database session
            pr_metadata: PR metadata dictionary

        Returns:
            PullRequest model instance
        """
        # Check if PR already exists
        db_pr = session.query(PullRequest).filter_by(pr_number=pr_metadata['pr_number']).first()

        if db_pr:
            # Update existing PR
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
        return db_pr

    def _collect_build_data(self, session: Session, pr_number: int, build_id: str, job_name: str):
        """Collect and store data for a single build.

        Args:
            session: Database session
            pr_number: Pull request number
            build_id: Build ID
            job_name: Prow job name
        """
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

    def _collect_pr_comments(self, session: Session, pr, pr_number: int):
        """Collect and store comments for a PR.

        Args:
            session: Database session
            pr: GitHub PullRequest object
            pr_number: Pull request number
        """
        # Check if comments already exist
        existing_count = session.query(PRComment).filter_by(pr_number=pr_number).count()
        if existing_count > 0:
            logger.info(f"PR #{pr_number}: {existing_count} comment(s) already cached, skipping")
            return

        # Get all comments
        logger.info(f"PR #{pr_number}: Fetching comments from GitHub...")
        comments = self.github_collector.get_all_pr_comments(pr)

        if not comments:
            logger.info(f"PR #{pr_number}: No comments found")
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
            logger.info(f"PR #{pr_number}: Stored {stored_count} comment(s) ({type_summary})")


@click.command()
@click.option('--config', default='config/config.yaml', help='Path to configuration file')
@click.option('--start-date', type=click.DateTime(formats=['%Y-%m-%d']), help='Start date (YYYY-MM-DD)')
@click.option('--end-date', type=click.DateTime(formats=['%Y-%m-%d']), help='End date (YYYY-MM-DD)')
@click.option('--skip-comments', is_flag=True, help='Skip collecting PR comments')
def main(config, start_date, end_date, skip_comments):
    """Collect CI audit data from GitHub and Prow."""
    # Load configuration
    cfg = Config(config)

    # Use dates from config if not specified
    if not start_date:
        start_date = datetime.strptime(cfg.get('collection.start_date'), '%Y-%m-%d').replace(tzinfo=timezone.utc)
    if not end_date:
        end_date = datetime.strptime(cfg.get('collection.end_date'), '%Y-%m-%d').replace(tzinfo=timezone.utc)

    logger.info(f"Configuration loaded from {config}")
    logger.info(f"Collection period: {start_date} to {end_date}")
    if skip_comments:
        logger.info("Comment collection disabled (--skip-comments)")

    # Run collection
    collector = DataCollector(cfg, collect_comments=not skip_comments)
    collector.collect_all(start_date, end_date)


if __name__ == '__main__':
    main()
