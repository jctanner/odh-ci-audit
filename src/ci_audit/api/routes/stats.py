"""API routes for statistics."""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from sqlalchemy import func, case

from ci_audit.api import get_db_session
from ci_audit.database.models import TestRun, PullRequest, TestCase

bp = Blueprint('stats', __name__, url_prefix='/api/stats')


@bp.route('/overview', methods=['GET'])
def get_overview():
    """Get overall statistics."""
    db = get_db_session()

    # Count total test runs
    total_runs = db.query(func.count(TestRun.id)).scalar() or 0

    # Count by result
    success_count = db.query(func.count(TestRun.id)).filter(
        TestRun.result == 'SUCCESS'
    ).scalar() or 0

    failure_count = db.query(func.count(TestRun.id)).filter(
        TestRun.result == 'FAILURE'
    ).scalar() or 0

    aborted_count = db.query(func.count(TestRun.id)).filter(
        TestRun.result == 'ABORTED'
    ).scalar() or 0

    # Count total PRs
    total_prs = db.query(func.count(PullRequest.pr_number.distinct())).scalar() or 0

    # Count total test cases
    total_test_cases = db.query(func.count(TestCase.id)).scalar() or 0

    # Count test cases by status
    passed_tests = db.query(func.count(TestCase.id)).filter(
        TestCase.status == 'passed'
    ).scalar() or 0

    failed_tests = db.query(func.count(TestCase.id)).filter(
        TestCase.status == 'failed'
    ).scalar() or 0

    skipped_tests = db.query(func.count(TestCase.id)).filter(
        TestCase.status == 'skipped'
    ).scalar() or 0

    # Calculate pass rate
    pass_rate = (success_count / total_runs * 100) if total_runs > 0 else 0

    return jsonify({
        'test_runs': {
            'total': total_runs,
            'success': success_count,
            'failure': failure_count,
            'aborted': aborted_count,
            'pass_rate': round(pass_rate, 2)
        },
        'pull_requests': {
            'total': total_prs
        },
        'test_cases': {
            'total': total_test_cases,
            'passed': passed_tests,
            'failed': failed_tests,
            'skipped': skipped_tests
        }
    })


@bp.route('/timeline', methods=['GET'])
def get_timeline():
    """Get test run results over time (daily aggregation)."""
    db = get_db_session()

    # Optional date range filters
    days = request.args.get('days', default=30, type=int)

    # Calculate the cutoff date
    from datetime import timedelta
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Query test runs grouped by date
    # Use func.date() to truncate to date, then count by result
    results = db.query(
        func.date(TestRun.started_at).label('date'),
        func.sum(case((TestRun.result == 'SUCCESS', 1), else_=0)).label('success'),
        func.sum(case((TestRun.result == 'FAILURE', 1), else_=0)).label('failure'),
        func.sum(case((TestRun.result == 'ABORTED', 1), else_=0)).label('aborted')
    ).filter(
        TestRun.started_at.isnot(None),
        TestRun.started_at >= cutoff_date
    ).group_by(
        func.date(TestRun.started_at)
    ).order_by(
        func.date(TestRun.started_at)
    ).all()

    # Format the results for the frontend
    timeline_data = {
        'dates': [],
        'success': [],
        'failure': [],
        'aborted': []
    }

    for row in results:
        timeline_data['dates'].append(row.date.isoformat() if row.date else None)
        timeline_data['success'].append(int(row.success or 0))
        timeline_data['failure'].append(int(row.failure or 0))
        timeline_data['aborted'].append(int(row.aborted or 0))

    return jsonify(timeline_data)


@bp.route('/duration', methods=['GET'])
def get_duration():
    """Get test run durations over time (daily aggregation in hours)."""
    db = get_db_session()

    # Optional date range filters
    days = request.args.get('days', default=30, type=int)

    # Calculate the cutoff date
    from datetime import timedelta
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Query test runs grouped by date, summing duration by result
    # Convert seconds to hours (divide by 3600)
    results = db.query(
        func.date(TestRun.started_at).label('date'),
        func.sum(case((TestRun.result == 'SUCCESS', TestRun.duration_seconds), else_=0)).label('success_seconds'),
        func.sum(case((TestRun.result == 'FAILURE', TestRun.duration_seconds), else_=0)).label('failure_seconds'),
        func.sum(case((TestRun.result == 'ABORTED', TestRun.duration_seconds), else_=0)).label('aborted_seconds')
    ).filter(
        TestRun.started_at.isnot(None),
        TestRun.started_at >= cutoff_date,
        TestRun.duration_seconds.isnot(None)
    ).group_by(
        func.date(TestRun.started_at)
    ).order_by(
        func.date(TestRun.started_at)
    ).all()

    # Format the results for the frontend (convert to hours)
    duration_data = {
        'dates': [],
        'success_hours': [],
        'failure_hours': [],
        'aborted_hours': []
    }

    for row in results:
        duration_data['dates'].append(row.date.isoformat() if row.date else None)
        # Convert seconds to hours and round to 2 decimal places
        duration_data['success_hours'].append(round((row.success_seconds or 0) / 3600, 2))
        duration_data['failure_hours'].append(round((row.failure_seconds or 0) / 3600, 2))
        duration_data['aborted_hours'].append(round((row.aborted_seconds or 0) / 3600, 2))

    return jsonify(duration_data)


@bp.route('/pr-metrics', methods=['GET'])
def get_pr_metrics():
    """Get PR metrics over time (average runs per PR and wait time)."""
    db = get_db_session()

    # Optional date range filters
    days = request.args.get('days', default=30, type=int)

    # Calculate the cutoff date
    from datetime import timedelta
    from sqlalchemy import distinct
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Query to get PR metrics grouped by date
    # For each day, calculate:
    # 1. Average number of test runs per PR
    # 2. Average wait time from PR creation to first test run

    # First, get PRs with their creation dates and first run times
    from sqlalchemy.sql import text

    # Use a subquery to get the first test run for each PR
    subquery = db.query(
        TestRun.pr_number,
        func.min(TestRun.started_at).label('first_run_at')
    ).filter(
        TestRun.started_at.isnot(None)
    ).group_by(
        TestRun.pr_number
    ).subquery()

    # Join with PRs to get creation dates and calculate wait times
    pr_data = db.query(
        func.date(PullRequest.created_at).label('date'),
        PullRequest.pr_number,
        func.count(TestRun.id).label('run_count'),
        func.extract('epoch', subquery.c.first_run_at - PullRequest.created_at).label('wait_seconds')
    ).join(
        TestRun, TestRun.pr_number == PullRequest.pr_number
    ).outerjoin(
        subquery, subquery.c.pr_number == PullRequest.pr_number
    ).filter(
        PullRequest.created_at >= cutoff_date,
        PullRequest.created_at.isnot(None)
    ).group_by(
        func.date(PullRequest.created_at),
        PullRequest.pr_number,
        subquery.c.first_run_at,
        PullRequest.created_at
    ).all()

    # Group by date and calculate averages
    from collections import defaultdict
    daily_metrics = defaultdict(lambda: {'run_counts': [], 'wait_times': []})

    for row in pr_data:
        if row.date:
            date_str = row.date.isoformat()
            daily_metrics[date_str]['run_counts'].append(row.run_count)
            if row.wait_seconds and row.wait_seconds > 0:
                # Convert to minutes and ensure it's a float
                daily_metrics[date_str]['wait_times'].append(float(row.wait_seconds) / 60)

    # Calculate averages and format response
    metrics_data = {
        'dates': [],
        'avg_runs_per_pr': [],
        'avg_wait_minutes': []
    }

    for date_str in sorted(daily_metrics.keys()):
        metrics = daily_metrics[date_str]
        metrics_data['dates'].append(date_str)

        # Average runs per PR
        avg_runs = sum(metrics['run_counts']) / len(metrics['run_counts']) if metrics['run_counts'] else 0
        metrics_data['avg_runs_per_pr'].append(round(avg_runs, 2))

        # Average wait time in minutes
        avg_wait = sum(metrics['wait_times']) / len(metrics['wait_times']) if metrics['wait_times'] else 0
        metrics_data['avg_wait_minutes'].append(round(avg_wait, 2))

    return jsonify(metrics_data)


@bp.route('/failures-by-suite', methods=['GET'])
def get_failures_by_suite():
    """Get failure counts grouped by test suite."""
    db = get_db_session()

    # Query failed test cases grouped by test suite
    results = db.query(
        TestCase.test_suite,
        func.count(TestCase.id).label('failures')
    ).filter(
        TestCase.status == 'failed'
    ).group_by(
        TestCase.test_suite
    ).order_by(
        func.count(TestCase.id).desc()
    ).all()

    suite_data = {
        'suites': [row.test_suite for row in results],
        'failures': [int(row.failures) for row in results]
    }

    return jsonify(suite_data)


@bp.route('/top-failing-tests', methods=['GET'])
def get_top_failing_tests():
    """Get top 10 most frequently failing tests."""
    db = get_db_session()

    limit = request.args.get('limit', default=10, type=int)

    # Query failed test cases grouped by test name
    results = db.query(
        TestCase.test_name,
        func.count(TestCase.id).label('failures')
    ).filter(
        TestCase.status == 'failed'
    ).group_by(
        TestCase.test_name
    ).order_by(
        func.count(TestCase.id).desc()
    ).limit(limit).all()

    test_data = {
        'tests': [row.test_name for row in results],
        'failures': [int(row.failures) for row in results]
    }

    return jsonify(test_data)


@bp.route('/failure-timeline', methods=['GET'])
def get_failure_timeline():
    """Get failed test cases over time (daily aggregation)."""
    db = get_db_session()

    # Optional date range filters
    days = request.args.get('days', default=30, type=int)

    # Calculate the cutoff date
    from datetime import timedelta
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Query test cases joined with test runs to get dates
    results = db.query(
        func.date(TestRun.started_at).label('date'),
        func.count(TestCase.id).label('failed_tests')
    ).join(
        TestCase, TestCase.run_id == TestRun.id
    ).filter(
        TestRun.started_at.isnot(None),
        TestRun.started_at >= cutoff_date,
        TestCase.status == 'failed'
    ).group_by(
        func.date(TestRun.started_at)
    ).order_by(
        func.date(TestRun.started_at)
    ).all()

    # Format the results
    timeline_data = {
        'dates': [row.date.isoformat() if row.date else None for row in results],
        'failed_tests': [int(row.failed_tests) for row in results]
    }

    return jsonify(timeline_data)
