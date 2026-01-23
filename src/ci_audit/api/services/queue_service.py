"""Service layer for work queue operations."""

from typing import Dict
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from ci_audit.database.models import WorkQueue, PullRequest
from ci_audit.config import Config
from ci_audit.collectors.github_collector import GitHubCollector


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
                'claimed_at': item.claimed_at.isoformat() if item.claimed_at else None,
                'completed_at': item.completed_at.isoformat() if item.completed_at else None,
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
