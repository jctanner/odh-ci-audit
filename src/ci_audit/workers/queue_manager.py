"""Work queue manager for coordinating parallel workers."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from ..database.models import WorkQueue


logger = logging.getLogger(__name__)


class QueueManager:
    """Manages work queue for parallel worker coordination.

    Uses PostgreSQL's SELECT FOR UPDATE SKIP LOCKED for lock-free
    work claiming and coordination between multiple workers.
    """

    def __init__(
        self,
        session: Session,
        worker_id: str,
        claim_timeout_minutes: int = 30,
        max_retries: int = 3
    ):
        """Initialize queue manager.

        Args:
            session: Database session
            worker_id: Unique worker identifier (hostname or container ID)
            claim_timeout_minutes: Minutes before stale claims are released
            max_retries: Maximum retry attempts for failed PRs
        """
        self.session = session
        self.worker_id = worker_id
        self.claim_timeout = timedelta(minutes=claim_timeout_minutes)
        self.max_retries = max_retries

    def claim_work(self) -> Optional[Dict[str, any]]:
        """Atomically claim next available PR from work queue.

        Uses PostgreSQL's SELECT FOR UPDATE SKIP LOCKED to prevent
        contention between workers. Claims are released after timeout
        if worker crashes or hangs.

        Returns:
            Dict with repo_owner, repo_name, pr_number, or None if no work available
        """
        # First, release any stale claims
        self._release_stale_claims()

        # Find and claim next pending work item
        # Priority: higher priority first, then oldest first
        work_item = (
            self.session.query(WorkQueue)
            .filter(WorkQueue.status == 'pending')
            .order_by(WorkQueue.priority.desc(), WorkQueue.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
            .first()
        )

        if work_item:
            # Claim the work
            work_item.status = 'claimed'
            work_item.worker_id = self.worker_id
            work_item.claimed_at = datetime.now(timezone.utc)
            work_item.attempt_count += 1
            self.session.commit()

            logger.info(
                f"Worker {self.worker_id}: Claimed {work_item.repo_owner}/{work_item.repo_name}#{work_item.pr_number} "
                f"(attempt {work_item.attempt_count}/{self.max_retries})"
            )
            return {
                'repo_owner': work_item.repo_owner,
                'repo_name': work_item.repo_name,
                'pr_number': work_item.pr_number
            }

        return None

    def mark_completed(self, repo_owner: str, repo_name: str, pr_number: int):
        """Mark a PR as successfully completed.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_number: Pull request number
        """
        work_item = (
            self.session.query(WorkQueue)
            .filter_by(repo_owner=repo_owner, repo_name=repo_name, pr_number=pr_number)
            .first()
        )

        if work_item:
            work_item.status = 'completed'
            work_item.completed_at = datetime.now(timezone.utc)
            work_item.last_error = None
            self.session.commit()
            logger.info(f"Worker {self.worker_id}: Completed {repo_owner}/{repo_name}#{pr_number}")
        else:
            logger.warning(f"Worker {self.worker_id}: {repo_owner}/{repo_name}#{pr_number} not found in queue")

    def mark_failed(self, repo_owner: str, repo_name: str, pr_number: int, error: str):
        """Mark a PR as failed, with retry logic.

        If attempt count is below max_retries, requeue as pending.
        Otherwise, mark as permanently failed.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_number: Pull request number
            error: Error message
        """
        work_item = (
            self.session.query(WorkQueue)
            .filter_by(repo_owner=repo_owner, repo_name=repo_name, pr_number=pr_number)
            .first()
        )

        if work_item:
            work_item.last_error = error[:1000]  # Truncate long errors

            if work_item.attempt_count >= self.max_retries:
                # Permanently failed
                work_item.status = 'failed'
                work_item.completed_at = datetime.now(timezone.utc)
                logger.error(
                    f"Worker {self.worker_id}: {repo_owner}/{repo_name}#{pr_number} FAILED "
                    f"after {work_item.attempt_count} attempts: {error[:100]}"
                )
            else:
                # Requeue for retry
                work_item.status = 'pending'
                work_item.worker_id = None
                work_item.claimed_at = None
                logger.warning(
                    f"Worker {self.worker_id}: {repo_owner}/{repo_name}#{pr_number} failed "
                    f"(attempt {work_item.attempt_count}/{self.max_retries}), "
                    f"requeuing: {error[:100]}"
                )

            self.session.commit()
        else:
            logger.warning(f"Worker {self.worker_id}: {repo_owner}/{repo_name}#{pr_number} not found in queue")

    def _release_stale_claims(self):
        """Release claims that have been held longer than timeout.

        This handles worker crashes or hangs. Claims older than
        claim_timeout are reset to pending status.
        """
        timeout_threshold = datetime.now(timezone.utc) - self.claim_timeout

        stale_claims = (
            self.session.query(WorkQueue)
            .filter(
                and_(
                    WorkQueue.status == 'claimed',
                    WorkQueue.claimed_at < timeout_threshold
                )
            )
            .all()
        )

        if stale_claims:
            for work_item in stale_claims:
                logger.warning(
                    f"Releasing stale claim: PR #{work_item.pr_number} "
                    f"by worker {work_item.worker_id} "
                    f"(claimed {work_item.claimed_at})"
                )
                work_item.status = 'pending'
                work_item.worker_id = None
                work_item.claimed_at = None

            self.session.commit()
            logger.info(f"Released {len(stale_claims)} stale claim(s)")

    def populate_queue(self, repo_owner: str, repo_name: str, pr_numbers: List[int], priority: int = 0):
        """Bulk populate work queue with PR numbers.

        Skips PRs that already exist in the queue for this repo.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_numbers: List of PR numbers to add to queue
            priority: Priority level (higher = more important)
        """
        # Get existing PRs in queue for this repo
        existing = set(
            row[0] for row in
            self.session.query(WorkQueue.pr_number)
            .filter_by(repo_owner=repo_owner, repo_name=repo_name)
            .all()
        )

        # Filter out PRs already in queue
        new_prs = [pr for pr in pr_numbers if pr not in existing]

        if not new_prs:
            logger.info(f"All PRs for {repo_owner}/{repo_name} already in work queue")
            return

        # Bulk insert new work items
        work_items = [
            WorkQueue(
                repo_owner=repo_owner,
                repo_name=repo_name,
                pr_number=pr_number,
                status='pending',
                priority=priority,
                attempt_count=0
            )
            for pr_number in new_prs
        ]

        self.session.bulk_save_objects(work_items)
        self.session.commit()

        logger.info(
            f"Added {len(new_prs)} PR(s) to work queue for {repo_owner}/{repo_name} "
            f"({len(existing)} already queued, {len(pr_numbers)} total)"
        )

    def get_queue_stats(self) -> dict:
        """Get current queue statistics.

        Returns:
            Dictionary with counts by status
        """
        from sqlalchemy import func

        stats = {}
        results = (
            self.session.query(
                WorkQueue.status,
                func.count(WorkQueue.id)
            )
            .group_by(WorkQueue.status)
            .all()
        )

        for status, count in results:
            stats[status] = count

        # Add zero counts for missing statuses
        for status in ['pending', 'claimed', 'completed', 'failed']:
            if status not in stats:
                stats[status] = 0

        return stats

    def reset_failed(self):
        """Reset all failed work items to pending for retry.

        Useful for re-attempting PRs after fixing issues.
        """
        failed_items = (
            self.session.query(WorkQueue)
            .filter_by(status='failed')
            .all()
        )

        if failed_items:
            for work_item in failed_items:
                work_item.status = 'pending'
                work_item.worker_id = None
                work_item.claimed_at = None
                work_item.completed_at = None
                work_item.attempt_count = 0

            self.session.commit()
            logger.info(f"Reset {len(failed_items)} failed item(s) to pending")
        else:
            logger.info("No failed items to reset")

    def reset_completed(self):
        """Reset all completed work items to pending for re-collection.

        Useful for re-collecting all PRs after bug fixes or to ensure
        incomplete/aborted builds are refetched.
        """
        completed_items = (
            self.session.query(WorkQueue)
            .filter_by(status='completed')
            .all()
        )

        if completed_items:
            for work_item in completed_items:
                work_item.status = 'pending'
                work_item.worker_id = None
                work_item.claimed_at = None
                work_item.completed_at = None
                work_item.attempt_count = 0
                work_item.last_error = None

            self.session.commit()
            logger.info(f"Reset {len(completed_items)} completed item(s) to pending")
        else:
            logger.info("No completed items to reset")

    def clear_queue(self):
        """Delete all items from work queue.

        WARNING: This is destructive and should only be used for testing
        or when repopulating the entire queue.
        """
        count = self.session.query(WorkQueue).delete()
        self.session.commit()
        logger.warning(f"Cleared {count} item(s) from work queue")
