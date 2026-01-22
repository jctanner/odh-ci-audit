#!/usr/bin/env python3
"""Producer script for populating work queue from GitHub PRs."""

import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click

from ci_audit.config import Config
from ci_audit.database.models import create_database, get_session
from ci_audit.collectors.github_collector import GitHubCollector
from ci_audit.workers.queue_manager import QueueManager


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Producer:
    """Producer for populating work queue with PRs from GitHub."""

    def __init__(self, config: Config):
        """Initialize producer.

        Args:
            config: Configuration object
        """
        self.config = config

        # Initialize database
        logger.info("Connecting to database...")
        self.engine = create_database(
            config.database_url,
            echo=config.get('database.echo_sql', False)
        )

        # Initialize GitHub collector
        logger.info("Initializing GitHub collector...")
        self.github_collector = GitHubCollector(
            token=config.github_token,
            repo_owner=config.github_repo_owner,
            repo_name=config.github_repo_name
        )

        logger.info("Producer initialization complete")

    def populate_queue(
        self,
        start_date: datetime,
        end_date: datetime,
        priority: int = 0,
        state: str = 'all'
    ):
        """Populate work queue with PRs from GitHub.

        Args:
            start_date: Start date for PR collection
            end_date: End date for PR collection
            priority: Priority level for queued items (higher = more important)
            state: PR state filter ('open', 'closed', 'all')
        """
        logger.info(f"Fetching PRs from {start_date} to {end_date} (state={state})")

        # Get all PRs in date range
        prs = self.github_collector.get_prs_in_date_range(
            start_date,
            end_date,
            state=state
        )

        if not prs:
            logger.warning("No PRs found in specified date range")
            return

        logger.info(f"Found {len(prs)} PRs from GitHub")

        # Extract PR numbers
        pr_numbers = [pr.number for pr in prs]

        # Populate queue
        session = get_session(self.engine)
        try:
            queue_mgr = QueueManager(
                session=session,
                worker_id='producer',
                claim_timeout_minutes=self.config.get('workers.claim_timeout_minutes', 30),
                max_retries=self.config.get('workers.max_retries', 3)
            )

            logger.info(f"Populating work queue with {len(pr_numbers)} PRs...")
            queue_mgr.populate_queue(
                repo_owner=self.config.github_repo_owner,
                repo_name=self.config.github_repo_name,
                pr_numbers=pr_numbers,
                priority=priority
            )

            # Show queue stats
            stats = queue_mgr.get_queue_stats()
            logger.info(
                f"Work queue populated. Stats: "
                f"{stats['pending']} pending, {stats['claimed']} claimed, "
                f"{stats['completed']} completed, {stats['failed']} failed"
            )

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to populate queue: {e}")
            raise
        finally:
            session.close()

        logger.info("Queue population complete!")

    def show_stats(self):
        """Display current work queue statistics."""
        session = get_session(self.engine)
        try:
            queue_mgr = QueueManager(
                session=session,
                worker_id='producer',
                claim_timeout_minutes=self.config.get('workers.claim_timeout_minutes', 30),
                max_retries=self.config.get('workers.max_retries', 3)
            )

            stats = queue_mgr.get_queue_stats()
            total = sum(stats.values())

            logger.info("=" * 60)
            logger.info("WORK QUEUE STATISTICS")
            logger.info("=" * 60)
            logger.info(f"  Pending:   {stats['pending']:6d} ({stats['pending']/total*100 if total > 0 else 0:.1f}%)")
            logger.info(f"  Claimed:   {stats['claimed']:6d} ({stats['claimed']/total*100 if total > 0 else 0:.1f}%)")
            logger.info(f"  Completed: {stats['completed']:6d} ({stats['completed']/total*100 if total > 0 else 0:.1f}%)")
            logger.info(f"  Failed:    {stats['failed']:6d} ({stats['failed']/total*100 if total > 0 else 0:.1f}%)")
            logger.info("-" * 60)
            logger.info(f"  Total:     {total:6d}")
            logger.info("=" * 60)

        finally:
            session.close()

    def reset_failed(self):
        """Reset all failed work items to pending for retry."""
        session = get_session(self.engine)
        try:
            queue_mgr = QueueManager(
                session=session,
                worker_id='producer',
                claim_timeout_minutes=self.config.get('workers.claim_timeout_minutes', 30),
                max_retries=self.config.get('workers.max_retries', 3)
            )

            logger.info("Resetting failed work items to pending...")
            queue_mgr.reset_failed()

            # Show updated stats
            stats = queue_mgr.get_queue_stats()
            logger.info(
                f"Queue stats after reset: "
                f"{stats['pending']} pending, {stats['claimed']} claimed, "
                f"{stats['completed']} completed, {stats['failed']} failed"
            )

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to reset failed items: {e}")
            raise
        finally:
            session.close()

    def reset_completed(self):
        """Reset all completed work items to pending for re-collection."""
        session = get_session(self.engine)
        try:
            queue_mgr = QueueManager(
                session=session,
                worker_id='producer',
                claim_timeout_minutes=self.config.get('workers.claim_timeout_minutes', 30),
                max_retries=self.config.get('workers.max_retries', 3)
            )

            logger.info("Resetting completed work items to pending...")
            queue_mgr.reset_completed()

            # Show updated stats
            stats = queue_mgr.get_queue_stats()
            logger.info(
                f"Queue stats after reset: "
                f"{stats['pending']} pending, {stats['claimed']} claimed, "
                f"{stats['completed']} completed, {stats['failed']} failed"
            )

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to reset completed items: {e}")
            raise
        finally:
            session.close()

    def clear_queue(self):
        """Clear all items from work queue."""
        session = get_session(self.engine)
        try:
            queue_mgr = QueueManager(
                session=session,
                worker_id='producer',
                claim_timeout_minutes=self.config.get('workers.claim_timeout_minutes', 30),
                max_retries=self.config.get('workers.max_retries', 3)
            )

            logger.warning("Clearing entire work queue...")
            queue_mgr.clear_queue()

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to clear queue: {e}")
            raise
        finally:
            session.close()


@click.command()
@click.option('--config', default='config/config.yaml', help='Path to configuration file')
@click.option('--start-date', type=click.DateTime(formats=['%Y-%m-%d']), help='Start date (YYYY-MM-DD)')
@click.option('--end-date', type=click.DateTime(formats=['%Y-%m-%d']), help='End date (YYYY-MM-DD)')
@click.option('--state', type=click.Choice(['open', 'closed', 'all']), default='all', help='PR state filter')
@click.option('--priority', default=0, type=int, help='Priority level (higher = more important)')
@click.option('--stats', is_flag=True, help='Show queue statistics and exit')
@click.option('--reset-failed', is_flag=True, help='Reset failed items to pending and exit')
@click.option('--reset-completed', is_flag=True, help='Reset completed items to pending and exit')
@click.option('--clear', is_flag=True, help='Clear entire work queue and exit')
def main(config, start_date, end_date, state, priority, stats, reset_failed, reset_completed, clear):
    """Populate work queue with PRs from GitHub.

    This script fetches PRs from GitHub and adds them to the work queue
    for parallel processing by workers.

    Examples:

        # Populate queue using dates from config
        python scripts/producer.py

        # Populate queue with custom date range
        python scripts/producer.py --start-date 2025-10-01 --end-date 2025-12-31

        # Only queue open PRs
        python scripts/producer.py --state open

        # Show queue statistics
        python scripts/producer.py --stats

        # Reset failed items to pending
        python scripts/producer.py --reset-failed

        # Reset completed items to pending (re-collect all PRs)
        python scripts/producer.py --reset-completed

        # Clear entire queue
        python scripts/producer.py --clear
    """
    # Load configuration
    cfg = Config(config)
    logger.info(f"Configuration loaded from {config}")
    logger.info(f"Database: {cfg.database_url.split('@')[-1] if '@' in cfg.database_url else cfg.database_url}")

    # Create producer
    producer = Producer(cfg)

    # Handle utility commands
    if stats:
        producer.show_stats()
        return

    if reset_failed:
        producer.reset_failed()
        return

    if reset_completed:
        producer.reset_completed()
        return

    if clear:
        # Require confirmation for destructive operation
        confirmation = input("Are you sure you want to clear the entire work queue? (yes/no): ")
        if confirmation.lower() == 'yes':
            producer.clear_queue()
        else:
            logger.info("Clear operation cancelled")
        return

    # Use dates from config if not specified
    if not start_date:
        start_date = datetime.strptime(cfg.get('collection.start_date'), '%Y-%m-%d').replace(tzinfo=timezone.utc)
    else:
        # Ensure command-line dates are timezone-aware
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

    if not end_date:
        end_date = datetime.strptime(cfg.get('collection.end_date'), '%Y-%m-%d').replace(tzinfo=timezone.utc)
    else:
        # Ensure command-line dates are timezone-aware
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

    logger.info(f"Queue population period: {start_date} to {end_date}")

    # Populate queue
    producer.populate_queue(start_date, end_date, priority=priority, state=state)


if __name__ == '__main__':
    main()
