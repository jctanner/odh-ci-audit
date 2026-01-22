"""Service layer for work queue operations."""

from typing import Dict
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from ci_audit.database.models import WorkQueue


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
