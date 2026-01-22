"""GitHub API client for collecting PR metadata."""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from github import Github, GithubException
from github.PullRequest import PullRequest as GithubPR


logger = logging.getLogger(__name__)


class GitHubCollector:
    """Client for collecting GitHub PR data using PyGithub."""

    def __init__(self, token: str, repo_owner: str, repo_name: str):
        """Initialize GitHub collector.

        Args:
            token: GitHub personal access token
            repo_owner: Repository owner (e.g., "opendatahub-io")
            repo_name: Repository name (e.g., "opendatahub-operator")
        """
        self.github = Github(token)
        self.repo = self.github.get_repo(f"{repo_owner}/{repo_name}")
        self.repo_owner = repo_owner
        self.repo_name = repo_name

        logger.info(f"Initialized GitHub collector for {repo_owner}/{repo_name}")

    def get_prs_in_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        state: str = "all"
    ) -> List[GithubPR]:
        """Get all pull requests within a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            state: PR state filter ("open", "closed", "all")

        Returns:
            List of PullRequest objects
        """
        logger.info(f"Fetching PRs from {start_date} to {end_date} (state={state})")

        prs = []
        try:
            # Get PRs sorted by creation date (newest first)
            all_prs = self.repo.get_pulls(
                state=state,
                sort="created",
                direction="desc"
            )

            for pr in all_prs:
                # Check if PR is within date range
                if pr.created_at < start_date:
                    # Since sorted by creation date desc, we can stop here
                    break

                if start_date <= pr.created_at <= end_date:
                    prs.append(pr)

            logger.info(f"Found {len(prs)} PRs in date range")

        except GithubException as e:
            logger.error(f"Failed to fetch PRs: {e}")
            raise

        return prs

    def get_pr_metadata(self, pr: GithubPR) -> Dict[str, Any]:
        """Extract metadata from a PR object.

        Args:
            pr: GitHub PullRequest object

        Returns:
            Dictionary with PR metadata
        """
        return {
            'pr_number': pr.number,
            'title': pr.title,
            'author': pr.user.login if pr.user else "unknown",
            'state': pr.state,
            'created_at': pr.created_at,
            'updated_at': pr.updated_at,
            'merged_at': pr.merged_at,
            'closed_at': pr.closed_at,
            'base_ref': pr.base.ref,
            'head_ref': pr.head.ref,
            'head_sha': pr.head.sha,
            'labels': [label.name for label in pr.labels],
            'is_draft': pr.draft,
            'metadata': {
                'additions': pr.additions,
                'deletions': pr.deletions,
                'changed_files': pr.changed_files,
                'commits': pr.commits,
                'comments': pr.comments,
                'review_comments': pr.review_comments,
                'mergeable': pr.mergeable,
                'mergeable_state': pr.mergeable_state,
            }
        }

    def get_pr_by_number(self, pr_number: int) -> Optional[GithubPR]:
        """Get a specific PR by number.

        Args:
            pr_number: Pull request number

        Returns:
            PullRequest object or None if not found
        """
        try:
            pr = self.repo.get_pull(pr_number)
            return pr
        except GithubException as e:
            logger.error(f"Failed to fetch PR #{pr_number}: {e}")
            return None

    def get_pr_commits(self, pr: GithubPR) -> List[str]:
        """Get list of commit SHAs for a PR.

        Args:
            pr: GitHub PullRequest object

        Returns:
            List of commit SHAs
        """
        try:
            commits = pr.get_commits()
            return [commit.sha for commit in commits]
        except GithubException as e:
            logger.error(f"Failed to fetch commits for PR #{pr.number}: {e}")
            return []

    def get_pr_issue_comments(self, pr: GithubPR) -> List[Dict[str, Any]]:
        """Get all issue comments for a PR.

        Args:
            pr: GitHub PullRequest object

        Returns:
            List of comment dictionaries
        """
        comments = []
        try:
            for comment in pr.get_issue_comments():
                comments.append({
                    'comment_id': comment.id,
                    'comment_type': 'issue_comment',
                    'author': comment.user.login if comment.user else "unknown",
                    'created_at': comment.created_at,
                    'updated_at': comment.updated_at,
                    'body': comment.body,
                    'metadata': {
                        'html_url': comment.html_url,
                    }
                })
        except GithubException as e:
            logger.error(f"Failed to fetch issue comments for PR #{pr.number}: {e}")

        return comments

    def get_pr_review_comments(self, pr: GithubPR) -> List[Dict[str, Any]]:
        """Get all review comments (inline code comments) for a PR.

        Args:
            pr: GitHub PullRequest object

        Returns:
            List of review comment dictionaries
        """
        comments = []
        try:
            for comment in pr.get_review_comments():
                comments.append({
                    'comment_id': comment.id,
                    'comment_type': 'review_comment',
                    'author': comment.user.login if comment.user else "unknown",
                    'created_at': comment.created_at,
                    'updated_at': comment.updated_at,
                    'body': comment.body,
                    'path': comment.path,
                    'line': comment.line,
                    'commit_id': comment.commit_id,
                    'in_reply_to_id': comment.in_reply_to_id,
                    'metadata': {
                        'html_url': comment.html_url,
                        'diff_hunk': comment.diff_hunk,
                        'original_line': comment.original_line,
                        'original_commit_id': comment.original_commit_id,
                    }
                })
        except GithubException as e:
            logger.error(f"Failed to fetch review comments for PR #{pr.number}: {e}")

        return comments

    def get_pr_reviews(self, pr: GithubPR) -> List[Dict[str, Any]]:
        """Get all reviews for a PR.

        Args:
            pr: GitHub PullRequest object

        Returns:
            List of review dictionaries
        """
        reviews = []
        try:
            for review in pr.get_reviews():
                reviews.append({
                    'comment_id': review.id,
                    'comment_type': 'review',
                    'author': review.user.login if review.user else "unknown",
                    'created_at': review.submitted_at if review.submitted_at else None,
                    'updated_at': None,  # Reviews don't have updated_at
                    'body': review.body,
                    'review_state': review.state,
                    'commit_id': review.commit_id,
                    'metadata': {
                        'html_url': review.html_url,
                    }
                })
        except GithubException as e:
            logger.error(f"Failed to fetch reviews for PR #{pr.number}: {e}")

        return reviews

    def get_all_pr_comments(self, pr: GithubPR) -> List[Dict[str, Any]]:
        """Get all comments (issue comments, review comments, and reviews) for a PR.

        Args:
            pr: GitHub PullRequest object

        Returns:
            List of all comment dictionaries
        """
        all_comments = []
        all_comments.extend(self.get_pr_issue_comments(pr))
        all_comments.extend(self.get_pr_review_comments(pr))
        all_comments.extend(self.get_pr_reviews(pr))

        logger.debug(f"PR #{pr.number}: {len(all_comments)} total comments")
        return all_comments

    def get_rate_limit(self) -> Dict[str, Any]:
        """Get current rate limit status.

        Returns:
            Dictionary with rate limit information
        """
        try:
            rate_limit = self.github.get_rate_limit()

            # PyGithub returns a RateLimitOverview object with core, search, graphql attributes
            # Each is a RateLimit object with limit, remaining, reset attributes
            if hasattr(rate_limit, 'core'):
                core = rate_limit.core
            else:
                # Fallback: assume the object itself is a RateLimit
                logger.debug(f"Rate limit object has no 'core' attribute, type: {type(rate_limit)}")
                core = rate_limit

            # Access attributes safely with getattr to handle API changes
            limit = getattr(core, 'limit', 5000)
            remaining = getattr(core, 'remaining', 5000)
            reset = getattr(core, 'reset', None)

            # Validate we got actual values
            if limit == 5000 and remaining == 5000:
                logger.debug(
                    f"Using default rate limit values. "
                    f"Core object type: {type(core)}, "
                    f"Available attributes: {dir(core)}"
                )

            return {
                'limit': limit,
                'remaining': remaining,
                'reset': reset,
                'used': limit - remaining,
            }
        except Exception as e:
            logger.warning(f"Failed to get rate limit: {e}. Using defaults.")
            # Return a default dict to avoid breaking the script
            return {
                'limit': 5000,
                'remaining': 5000,
                'reset': None,
                'used': 0
            }

    def close(self):
        """Close GitHub client."""
        if hasattr(self.github, 'close'):
            self.github.close()
