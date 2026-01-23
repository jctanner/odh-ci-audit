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
