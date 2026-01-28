"""Service layer for test run operations."""

from typing import Dict, List, Optional
from datetime import timezone
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from ci_audit.database.models import TestRun, PullRequest, TestCase


class TestRunService:
    """Business logic for test run operations."""

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_test_runs(
        self,
        filters: Optional[Dict] = None,
        page: int = 1,
        per_page: int = 50
    ) -> Dict:
        """
        Get paginated list of test runs with filters.

        Args:
            filters: Optional dict with keys: repo_owner, repo_name, pr_number, job_name, sort_by, sort_order
            page: Page number (1-indexed)
            per_page: Results per page

        Returns:
            Dict with keys: test_runs, total, page, per_page, total_pages
        """
        if filters is None:
            filters = {}

        # Build base query with join to pull_requests
        query = self.db.query(TestRun).join(PullRequest)

        # Filter out incomplete runs by default (those without started_at)
        show_incomplete = filters.get('show_incomplete', False)
        if not show_incomplete:
            query = query.filter(TestRun.started_at.isnot(None))

        # Apply filters
        if 'repo_owner' in filters and filters['repo_owner']:
            query = query.filter(PullRequest.repo_owner == filters['repo_owner'])

        if 'repo_name' in filters and filters['repo_name']:
            query = query.filter(PullRequest.repo_name == filters['repo_name'])

        if 'pr_number' in filters and filters['pr_number']:
            query = query.filter(TestRun.pr_number == int(filters['pr_number']))

        if 'job_name' in filters and filters['job_name']:
            # Support partial match for job name
            query = query.filter(TestRun.job_name.ilike(f"%{filters['job_name']}%"))

        if 'result' in filters and filters['result']:
            query = query.filter(TestRun.result == filters['result'])

        # Get total count
        total = query.count()

        # Apply sorting
        sort_by = filters.get('sort_by', 'started_at')
        sort_order = filters.get('sort_order', 'desc')

        # Map column names to SQLAlchemy model attributes
        sort_column_map = {
            'build_id': TestRun.build_id,
            'pr_number': TestRun.pr_number,
            'job_name': TestRun.job_name,
            'result': TestRun.result,
            'started_at': TestRun.started_at,
            'duration_seconds': TestRun.duration_seconds
        }

        # Get the column to sort by (default to started_at if invalid)
        sort_column = sort_column_map.get(sort_by, TestRun.started_at)

        # Apply sort direction
        if sort_order == 'asc':
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Apply pagination
        offset = (page - 1) * per_page
        test_runs = query.offset(offset).limit(per_page).all()

        # Calculate total pages
        total_pages = (total + per_page - 1) // per_page

        # Convert to dict format
        test_runs_data = [self._test_run_to_dict(tr) for tr in test_runs]

        return {
            'test_runs': test_runs_data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages
        }

    def get_test_run_detail(self, build_id: str) -> Optional[Dict]:
        """
        Get detailed information for a single test run.

        Args:
            build_id: Unique build identifier

        Returns:
            Dict with test run details and related data, or None if not found
        """
        test_run = self.db.query(TestRun).filter(TestRun.build_id == build_id).first()

        if not test_run:
            return None

        # Get related pull request
        pr = test_run.pull_request

        # Get test case counts using run_id
        total_tests = self.db.query(func.count(TestCase.id)).filter(
            TestCase.run_id == test_run.id
        ).scalar()

        passed_tests = self.db.query(func.count(TestCase.id)).filter(
            TestCase.run_id == test_run.id,
            TestCase.status == 'passed'
        ).scalar()

        failed_tests = self.db.query(func.count(TestCase.id)).filter(
            TestCase.run_id == test_run.id,
            TestCase.status == 'failed'
        ).scalar()

        skipped_tests = self.db.query(func.count(TestCase.id)).filter(
            TestCase.run_id == test_run.id,
            TestCase.status == 'skipped'
        ).scalar()

        # Set result to "PENDING" if NULL (job hasn't completed yet)
        result = test_run.result if test_run.result else "PENDING"

        return {
            'build_id': test_run.build_id,
            'pr_number': test_run.pr_number,
            'job_name': test_run.job_name,
            'result': result,
            'started_at': test_run.started_at.replace(tzinfo=timezone.utc).isoformat() if test_run.started_at else None,
            'finished_at': test_run.finished_at.replace(tzinfo=timezone.utc).isoformat() if test_run.finished_at else None,
            'duration_seconds': test_run.duration_seconds,
            'gcs_path': test_run.gcs_path,
            'e2e_log_path': test_run.e2e_log_path,
            'diagnostic_summary': test_run.diagnostic_summary,
            'pull_request': {
                'pr_number': pr.pr_number,
                'repo_owner': pr.repo_owner,
                'repo_name': pr.repo_name,
                'title': pr.title,
                'author': pr.author,
                'state': pr.state,
                'created_at': pr.created_at.replace(tzinfo=timezone.utc).isoformat() if pr.created_at else None,
                'merged_at': pr.merged_at.replace(tzinfo=timezone.utc).isoformat() if pr.merged_at else None,
            } if pr else None,
            'test_stats': {
                'total': total_tests or 0,
                'passed': passed_tests or 0,
                'failed': failed_tests or 0,
                'skipped': skipped_tests or 0
            }
        }

    def get_test_cases(
        self,
        build_id: str,
        status_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Get test cases for a build.

        Args:
            build_id: Unique build identifier
            status_filter: Optional filter for test case status (passed/failed/skipped)

        Returns:
            List of test case dicts
        """
        # First get the test run to get the run_id
        test_run = self.db.query(TestRun).filter(TestRun.build_id == build_id).first()

        if not test_run:
            return []

        # Query test cases using run_id
        query = self.db.query(TestCase).filter(TestCase.run_id == test_run.id)

        if status_filter:
            query = query.filter(TestCase.status == status_filter)

        test_cases = query.all()

        return [self._test_case_to_dict(tc) for tc in test_cases]

    def _test_run_to_dict(self, test_run: TestRun) -> Dict:
        """Convert TestRun model to dict."""
        pr = test_run.pull_request

        # Set result to "PENDING" if NULL (job hasn't completed yet)
        result = test_run.result if test_run.result else "PENDING"

        return {
            'build_id': test_run.build_id,
            'pr_number': test_run.pr_number,
            'job_name': test_run.job_name,
            'result': result,
            'started_at': test_run.started_at.replace(tzinfo=timezone.utc).isoformat() if test_run.started_at else None,
            'finished_at': test_run.finished_at.replace(tzinfo=timezone.utc).isoformat() if test_run.finished_at else None,
            'duration_seconds': test_run.duration_seconds,
            'gcs_path': test_run.gcs_path,
            'e2e_log_path': test_run.e2e_log_path,
            'repo_owner': pr.repo_owner if pr else None,
            'repo_name': pr.repo_name if pr else None,
            'pr_title': pr.title if pr else None
        }

    def _test_case_to_dict(self, test_case: TestCase) -> Dict:
        """Convert TestCase model to dict."""
        return {
            'id': test_case.id,
            'test_suite': test_case.test_suite,
            'test_name': test_case.test_name,
            'status': test_case.status,
            'duration_seconds': test_case.duration_seconds,
            'failure_message': test_case.failure_message,
            'stacktrace': test_case.failure_stacktrace
        }

    def get_test_run_summary(self, build_id: str) -> Optional[Dict]:
        """
        Get aggregated summary for a test run.

        Returns test counts, duration, and result status.
        """
        # Get the test run
        test_run = self.db.query(TestRun).filter(
            TestRun.build_id == build_id
        ).first()

        if not test_run:
            return None

        # Count test cases by status
        total_tests = self.db.query(func.count(TestCase.id)).filter(
            TestCase.run_id == test_run.id
        ).scalar() or 0

        passed_tests = self.db.query(func.count(TestCase.id)).filter(
            TestCase.run_id == test_run.id,
            TestCase.status == 'passed'
        ).scalar() or 0

        failed_tests = self.db.query(func.count(TestCase.id)).filter(
            TestCase.run_id == test_run.id,
            TestCase.status == 'failed'
        ).scalar() or 0

        skipped_tests = self.db.query(func.count(TestCase.id)).filter(
            TestCase.run_id == test_run.id,
            TestCase.status == 'skipped'
        ).scalar() or 0

        # Set result to "PENDING" if NULL
        result = test_run.result if test_run.result else "PENDING"

        return {
            'build_id': build_id,
            'pr_number': test_run.pr_number,
            'job_name': test_run.job_name,
            'result': result,
            'total_tests': total_tests,
            'passed': passed_tests,
            'failed': failed_tests,
            'skipped': skipped_tests,
            'duration_seconds': test_run.duration_seconds,
            'started_at': test_run.started_at.replace(tzinfo=timezone.utc).isoformat() if test_run.started_at else None,
            'finished_at': test_run.finished_at.replace(tzinfo=timezone.utc).isoformat() if test_run.finished_at else None
        }

    def get_test_failures(self, build_id: str) -> List[Dict]:
        """
        Get only failed test cases for a test run.

        Returns detailed failure information including messages and stacktraces.
        """
        # Get the test run
        test_run = self.db.query(TestRun).filter(
            TestRun.build_id == build_id
        ).first()

        if not test_run:
            return []

        # Get failed test cases
        failed_tests = self.db.query(TestCase).filter(
            TestCase.run_id == test_run.id,
            TestCase.status == 'failed'
        ).all()

        return [
            {
                'test_suite': tc.test_suite,
                'test_name': tc.test_name,
                'duration_seconds': tc.duration_seconds,
                'failure_message': tc.failure_message,
                'failure_type': tc.failure_type,
                'stacktrace': tc.failure_stacktrace,
                'system_out': tc.system_out,
                'system_err': tc.system_err
            }
            for tc in failed_tests
        ]
