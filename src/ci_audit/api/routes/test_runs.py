"""API routes for test runs."""

from flask import Blueprint, jsonify, request

from ci_audit.api import get_db_session
from ci_audit.api.services.test_run_service import TestRunService

bp = Blueprint('test_runs', __name__, url_prefix='/api/test-runs')


@bp.route('', methods=['GET'])
def list_test_runs():
    """List test runs with optional filters and pagination."""
    # Get query parameters
    filters = {}
    if request.args.get('repo_owner'):
        filters['repo_owner'] = request.args.get('repo_owner')
    if request.args.get('repo_name'):
        filters['repo_name'] = request.args.get('repo_name')
    if request.args.get('pr_number'):
        filters['pr_number'] = request.args.get('pr_number')
    if request.args.get('job_name'):
        filters['job_name'] = request.args.get('job_name')
    if request.args.get('result'):
        filters['result'] = request.args.get('result')

    # Sort parameters
    if request.args.get('sort_by'):
        filters['sort_by'] = request.args.get('sort_by')
    if request.args.get('sort_order'):
        filters['sort_order'] = request.args.get('sort_order')

    # Show incomplete runs toggle
    if request.args.get('show_incomplete') == 'true':
        filters['show_incomplete'] = True

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    # Get test runs from service
    db = get_db_session()
    service = TestRunService(db)
    result = service.get_test_runs(filters, page, per_page)

    return jsonify(result)


@bp.route('/<build_id>', methods=['GET'])
def get_test_run(build_id):
    """Get detailed information for a single test run."""
    db = get_db_session()
    service = TestRunService(db)
    result = service.get_test_run_detail(build_id)

    if result is None:
        return jsonify({'error': 'Test run not found'}), 404

    return jsonify(result)


@bp.route('/<build_id>/test-cases', methods=['GET'])
def get_test_cases(build_id):
    """Get test cases for a build."""
    status_filter = request.args.get('status')

    db = get_db_session()
    service = TestRunService(db)
    test_cases = service.get_test_cases(build_id, status_filter)

    return jsonify({
        'build_id': build_id,
        'test_cases': test_cases
    })
