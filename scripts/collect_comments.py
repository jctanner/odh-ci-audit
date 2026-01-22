#!/usr/bin/env python3
"""Collect PR comments from GitHub and store in database."""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from src.ci_audit.collectors.github_collector import GitHubCollector
from src.ci_audit.database.models import create_database, get_session, PRComment, PullRequest
import yaml


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration from YAML file."""
    # Load environment variables from .env file
    load_dotenv()

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Expand environment variables
    if config['github']['token'].startswith('${') and config['github']['token'].endswith('}'):
        env_var = config['github']['token'][2:-1]
        config['github']['token'] = os.getenv(env_var)

    return config


def collect_pr_comments(github_collector, session, pr_number: int, force: bool = False):
    """Collect comments for a single PR.

    Args:
        github_collector: GitHubCollector instance
        session: Database session
        pr_number: PR number
        force: Force re-collection even if comments exist
    """
    # Check if comments already exist
    if not force:
        existing_count = session.query(PRComment).filter_by(pr_number=pr_number).count()
        if existing_count > 0:
            logger.debug(f"PR #{pr_number}: {existing_count} comments already exist, skipping")
            return existing_count

    # Get PR
    pr = github_collector.get_pr_by_number(pr_number)
    if not pr:
        logger.warning(f"PR #{pr_number} not found")
        return 0

    # Get all comments
    comments = github_collector.get_all_pr_comments(pr)

    if not comments:
        logger.debug(f"PR #{pr_number}: No comments found")
        return 0

    # Store comments in database
    stored_count = 0
    for comment_data in comments:
        # Check if comment already exists
        existing = session.query(PRComment).filter_by(
            comment_id=comment_data['comment_id']
        ).first()

        if existing and not force:
            logger.debug(f"Comment {comment_data['comment_id']} already exists, skipping")
            continue

        if existing and force:
            # Update existing comment
            for key, value in comment_data.items():
                if key == 'metadata':
                    setattr(existing, 'comment_metadata', json.dumps(value))
                elif hasattr(existing, key):
                    setattr(existing, key, value)
            stored_count += 1
        else:
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
        session.commit()
        logger.info(f"PR #{pr_number}: Stored {stored_count} comments")

    return stored_count


def main():
    """Main collection function."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Collect PR comments from GitHub')
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of PRs to process (for testing)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-collection of comments even if they exist'
    )
    args = parser.parse_args()

    # Load configuration
    config = load_config()

    # Validate GitHub token
    if not config['github']['token']:
        logger.error(
            "GitHub token not found. Please ensure:\n"
            "1. .env file exists with GITHUB_TOKEN=your_token\n"
            "2. config/config.yaml has github.token: ${GITHUB_TOKEN}"
        )
        sys.exit(1)

    logger.info(f"GitHub token loaded (length: {len(config['github']['token'])} chars)")

    # Initialize database
    db_path = config['database']['path']
    engine = create_database(f"sqlite:///{db_path}")
    session = get_session(engine)

    # Initialize GitHub collector
    github_collector = GitHubCollector(
        token=config['github']['token'],
        repo_owner=config['github']['repo_owner'],
        repo_name=config['github']['repo_name']
    )

    # Get all PRs from database
    query = session.query(PullRequest.pr_number).order_by(PullRequest.pr_number.desc())
    if args.limit:
        query = query.limit(args.limit)
    prs = query.all()
    total_prs = len(prs)

    logger.info(f"Found {total_prs} PRs in database")
    if args.limit:
        logger.info(f"Limiting collection to {args.limit} PRs (--limit)")
    if args.force:
        logger.info("Force mode enabled: will re-collect existing comments")
    logger.info("Starting comment collection...")

    total_comments = 0
    processed = 0
    errors = 0

    start_time = time.time()

    for (pr_number,) in prs:
        try:
            comment_count = collect_pr_comments(github_collector, session, pr_number, force=args.force)
            total_comments += comment_count
            processed += 1

            if processed % 10 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = total_prs - processed
                eta = remaining / rate if rate > 0 else 0

                # Check rate limit
                rate_limit = github_collector.get_rate_limit()

                logger.info(
                    f"Progress: {processed}/{total_prs} PRs "
                    f"({processed*100/total_prs:.1f}%) | "
                    f"{total_comments} comments | "
                    f"Rate: {rate:.1f} PR/s | "
                    f"ETA: {eta/60:.1f}m | "
                    f"API: {rate_limit.get('remaining', '?')}/{rate_limit.get('limit', '?')}"
                )

                # Sleep if rate limit is low
                if rate_limit.get('remaining', 5000) < 100:
                    reset_time = rate_limit.get('reset')
                    if reset_time:
                        wait_time = (reset_time - datetime.now(timezone.utc)).total_seconds()
                        if wait_time > 0:
                            logger.warning(f"Rate limit low, sleeping for {wait_time:.0f}s")
                            time.sleep(wait_time + 1)

        except Exception as e:
            logger.error(f"Error collecting comments for PR #{pr_number}: {e}")
            errors += 1
            if errors > 10:
                logger.error("Too many errors, stopping collection")
                break

    elapsed = time.time() - start_time

    logger.info("=" * 60)
    logger.info("Collection complete!")
    logger.info(f"Processed: {processed} PRs")
    logger.info(f"Total comments: {total_comments}")
    logger.info(f"Errors: {errors}")
    logger.info(f"Time: {elapsed/60:.1f} minutes")
    logger.info("=" * 60)

    # Close connections
    session.close()
    github_collector.close()


if __name__ == "__main__":
    main()
