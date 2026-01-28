"""Service layer for work queue operations."""

from typing import Dict
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from ci_audit.database.models import WorkQueue, PullRequest, TestRun
from ci_audit.config import Config
from ci_audit.collectors.github_collector import GitHubCollector
from ci_audit.collectors.gcs_collector import GCSCollector
import requests
import xml.etree.ElementTree as ET


class QueueService:
    """Business logic for work queue management."""

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_queue_stats(self) -> Dict:
        """
        Get work queue statistics.

        Returns:
            Dict with queue status counts and recent activity
        """
        # Count by status
        stats = {}
        for status in ['pending', 'claimed', 'completed', 'failed']:
            count = self.db.query(func.count(WorkQueue.id)).filter(
                WorkQueue.status == status
            ).scalar()
            stats[status] = count or 0

        # Total count
        stats['total'] = sum(stats.values())

        # Get recent activity (last 10 items, ordered by ID)
        recent = self.db.query(WorkQueue).order_by(
            WorkQueue.id.desc()
        ).limit(10).all()

        stats['recent_activity'] = [
            {
                'pr_number': item.pr_number,
                'repo_owner': item.repo_owner,
                'repo_name': item.repo_name,
                'status': item.status,
                'worker_id': item.worker_id,
                'claimed_at': item.claimed_at.replace(tzinfo=timezone.utc).isoformat() if item.claimed_at else None,
                'completed_at': item.completed_at.replace(tzinfo=timezone.utc).isoformat() if item.completed_at else None,
                'attempt_count': item.attempt_count
            }
            for item in recent
        ]

        return stats

    def trigger_collection(
        self,
        pr_number: int,
        repo_owner: str,
        repo_name: str,
        force: bool = False
    ) -> Dict:
        """
        Trigger collection for a PR.

        Args:
            pr_number: PR number to collect
            repo_owner: Repository owner
            repo_name: Repository name
            force: If True, reset status to pending even if already completed

        Returns:
            Dict with status and message
        """
        # Check if item already exists
        existing = self.db.query(WorkQueue).filter(
            WorkQueue.pr_number == pr_number,
            WorkQueue.repo_owner == repo_owner,
            WorkQueue.repo_name == repo_name
        ).first()

        if existing:
            if existing.status == 'completed' and not force:
                return {
                    'status': 'skipped',
                    'message': f'PR {pr_number} already completed. Use force=true to re-collect.'
                }

            # Reset to pending
            existing.status = 'pending'
            existing.worker_id = None
            existing.claimed_at = None
            existing.completed_at = None
            existing.last_error = None

            if force:
                existing.attempt_count = 0

            self.db.commit()

            return {
                'status': 'reset',
                'message': f'PR {pr_number} reset to pending'
            }

        else:
            # Create new work item
            work_item = WorkQueue(
                pr_number=pr_number,
                repo_owner=repo_owner,
                repo_name=repo_name,
                status='pending',
                attempt_count=0
            )

            self.db.add(work_item)
            self.db.commit()

            return {
                'status': 'created',
                'message': f'PR {pr_number} added to queue'
            }

    def reset_failed(self) -> Dict:
        """
        Reset all failed items to pending for retry.

        Returns:
            Dict with count of reset items
        """
        failed_items = self.db.query(WorkQueue).filter(
            WorkQueue.status == 'failed'
        ).all()

        count = len(failed_items)

        for item in failed_items:
            item.status = 'pending'
            item.worker_id = None
            item.claimed_at = None
            item.last_error = None

        self.db.commit()

        return {
            'status': 'success',
            'message': f'Reset {count} failed items to pending'
        }

    def reset_completed(self) -> Dict:
        """
        Reset all completed items to pending for re-collection.

        Returns:
            Dict with count of reset items
        """
        completed_items = self.db.query(WorkQueue).filter(
            WorkQueue.status == 'completed'
        ).all()

        count = len(completed_items)

        for item in completed_items:
            item.status = 'pending'
            item.worker_id = None
            item.claimed_at = None
            item.completed_at = None
            item.last_error = None
            item.attempt_count = 0

        self.db.commit()

        return {
            'status': 'success',
            'message': f'Reset {count} completed items to pending'
        }

    def collect_new_prs(self) -> Dict:
        """
        Collect new PRs from GitHub since the last PR in the database.

        Returns:
            Dict with status, count of PRs added, and date range
        """
        try:
            # Load config
            config = Config('config/config.yaml')

            # Get the most recent PR creation date from the database
            latest_pr = self.db.query(PullRequest).order_by(
                PullRequest.created_at.desc()
            ).first()

            if latest_pr and latest_pr.created_at:
                # Start from the day after the latest PR (to avoid duplicates)
                # Database datetimes are naive (no timezone), so add UTC timezone
                start_date = latest_pr.created_at.replace(tzinfo=timezone.utc)
            else:
                # No PRs in database, use a default starting point (30 days ago)
                start_date = datetime.now(timezone.utc) - timedelta(days=30)

            # End date is today
            end_date = datetime.now(timezone.utc)

            # Initialize GitHub collector
            github_collector = GitHubCollector(
                token=config.github_token,
                repo_owner=config.github_repo_owner,
                repo_name=config.github_repo_name
            )

            # Fetch PRs from GitHub
            prs = github_collector.get_prs_in_date_range(
                start_date,
                end_date,
                state='all'  # Get both open and closed PRs
            )

            if not prs:
                return {
                    'status': 'success',
                    'message': 'No new PRs found',
                    'count': 0,
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                }

            # Add PRs to the work queue (skip duplicates)
            added_count = 0
            skipped_count = 0

            for pr in prs:
                # Check if already in queue
                existing = self.db.query(WorkQueue).filter(
                    WorkQueue.pr_number == pr.number,
                    WorkQueue.repo_owner == config.github_repo_owner,
                    WorkQueue.repo_name == config.github_repo_name
                ).first()

                if existing:
                    skipped_count += 1
                    continue

                # Add to queue
                work_item = WorkQueue(
                    pr_number=pr.number,
                    repo_owner=config.github_repo_owner,
                    repo_name=config.github_repo_name,
                    status='pending',
                    attempt_count=0,
                    priority=0
                )
                self.db.add(work_item)
                added_count += 1

            self.db.commit()

            return {
                'status': 'success',
                'message': f'Added {added_count} new PRs to queue ({skipped_count} already exist)',
                'count': added_count,
                'skipped': skipped_count,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'pr_numbers': [pr.number for pr in prs]
            }

        except Exception as e:
            self.db.rollback()
            return {
                'status': 'error',
                'message': f'Failed to collect new PRs: {str(e)}'
            }

    def validate_pr(self, pr_number: int, repo_owner: str = None, repo_name: str = None) -> Dict:
        """
        Validate that we have the latest test runs for a PR by comparing with GCS.

        Args:
            pr_number: PR number to validate
            repo_owner: Repository owner (optional, defaults to config)
            repo_name: Repository name (optional, defaults to config)

        Returns:
            Dict with validation results showing database vs GCS comparison
        """
        try:
            # Load config for GCS settings
            config = Config('config/config.yaml')

            # Use provided values or fall back to config
            if not repo_owner:
                repo_owner = config.get('github.repo_owner')
            if not repo_name:
                repo_name = config.get('github.repo_name')

            # Get latest build IDs from database for this PR, grouped by job type
            db_builds = self.db.query(
                TestRun.job_name,
                func.max(TestRun.build_id).label('latest_build_id'),
                func.count(TestRun.id).label('total_runs')
            ).filter(
                TestRun.pr_number == pr_number
            ).group_by(
                TestRun.job_name
            ).all()

            if not db_builds:
                return {
                    'status': 'not_found',
                    'message': f'No test runs found for PR #{pr_number} in database',
                    'pr_number': pr_number
                }

            # Query GCS to get available job types and their latest builds
            gcs_base_url = f"https://storage.googleapis.com/{config.get('gcs.bucket')}"
            pr_path = f"pr-logs/pull/{repo_owner}_{repo_name}/{pr_number}/"

            # Get list of job directories from GCS
            response = requests.get(
                f"{gcs_base_url}/?prefix={pr_path}&delimiter=/",
                timeout=30
            )
            response.raise_for_status()

            # Parse XML response to get job directories
            root = ET.fromstring(response.content)
            ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}
            job_prefixes = root.findall('.//s3:Prefix', ns)

            gcs_jobs = {}
            for prefix_elem in job_prefixes:
                prefix = prefix_elem.text
                if prefix and prefix != pr_path:
                    # Extract job name from prefix
                    job_name = prefix.rstrip('/').split('/')[-1]

                    # Get builds for this job
                    builds_response = requests.get(
                        f"{gcs_base_url}/?prefix={prefix}&delimiter=/",
                        timeout=30
                    )
                    builds_response.raise_for_status()

                    # Parse to get build IDs
                    builds_root = ET.fromstring(builds_response.content)
                    build_prefixes = builds_root.findall('.//s3:Prefix', ns)

                    build_ids = []
                    for build_prefix_elem in build_prefixes:
                        build_prefix = build_prefix_elem.text
                        if build_prefix and build_prefix != prefix:
                            # Extract build ID
                            build_id = build_prefix.rstrip('/').split('/')[-1]
                            if build_id.isdigit():
                                build_ids.append(build_id)

                    if build_ids:
                        # Get the latest build ID
                        latest_build = max(build_ids, key=lambda x: int(x))
                        gcs_jobs[job_name] = {
                            'latest_build_id': latest_build,
                            'total_builds': len(build_ids)
                        }

            # Compare database vs GCS
            job_comparisons = []
            all_current = True

            db_jobs_map = {row.job_name: row for row in db_builds}

            # Check all GCS jobs
            for job_name, gcs_info in gcs_jobs.items():
                db_row = db_jobs_map.get(job_name)

                if db_row:
                    db_build_id = db_row.latest_build_id
                    gcs_build_id = gcs_info['latest_build_id']
                    is_current = (db_build_id == gcs_build_id)

                    if not is_current:
                        all_current = False

                    job_comparisons.append({
                        'job_name': job_name,
                        'db_latest_build': db_build_id,
                        'gcs_latest_build': gcs_build_id,
                        'is_current': is_current,
                        'db_total_runs': db_row.total_runs,
                        'gcs_total_builds': gcs_info['total_builds']
                    })
                else:
                    # Job exists in GCS but not in DB
                    all_current = False
                    job_comparisons.append({
                        'job_name': job_name,
                        'db_latest_build': None,
                        'gcs_latest_build': gcs_info['latest_build_id'],
                        'is_current': False,
                        'db_total_runs': 0,
                        'gcs_total_builds': gcs_info['total_builds']
                    })

            # Check for jobs in DB that aren't in GCS (shouldn't happen)
            for job_name, db_row in db_jobs_map.items():
                if job_name not in gcs_jobs:
                    job_comparisons.append({
                        'job_name': job_name,
                        'db_latest_build': db_row.latest_build_id,
                        'gcs_latest_build': None,
                        'is_current': True,  # DB has it but GCS doesn't
                        'db_total_runs': db_row.total_runs,
                        'gcs_total_builds': 0
                    })

            return {
                'status': 'success',
                'pr_number': pr_number,
                'is_current': all_current,
                'total_job_types': len(job_comparisons),
                'current_job_types': sum(1 for j in job_comparisons if j['is_current']),
                'jobs': job_comparisons,
                'message': f'PR #{pr_number} is {"up-to-date" if all_current else "missing some builds"}'
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to validate PR #{pr_number}: {str(e)}'
            }
