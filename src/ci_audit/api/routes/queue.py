"""API routes for work queue management."""

from flask import Blueprint, jsonify, request

from ci_audit.api import get_db_session
from ci_audit.api.services.queue_service import QueueService

bp = Blueprint('queue', __name__, url_prefix='/api/queue')


@bp.route('/stats', methods=['GET'])
def get_stats():
    """Get work queue statistics."""
    db = get_db_session()
    service = QueueService(db)
    stats = service.get_queue_stats()

    return jsonify(stats)


@bp.route('/trigger', methods=['POST'])
def trigger_collection():
    """Trigger collection for one or more PRs (comma-separated)."""
    data = request.get_json()

    # Validate required fields
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    pr_number = data.get('pr_number')
    repo_owner = data.get('repo_owner')
    repo_name = data.get('repo_name')

    if not all([pr_number, repo_owner, repo_name]):
        return jsonify({'error': 'pr_number, repo_owner, and repo_name are required'}), 400

    force = data.get('force', False)

    # Parse PR numbers (can be single int or comma-separated string)
    pr_numbers = []
    if isinstance(pr_number, int):
        pr_numbers = [pr_number]
    elif isinstance(pr_number, str):
        # Split by comma and strip whitespace
        pr_numbers = [int(num.strip()) for num in pr_number.split(',') if num.strip()]
    else:
        return jsonify({'error': 'pr_number must be an integer or comma-separated string'}), 400

    if not pr_numbers:
        return jsonify({'error': 'No valid PR numbers provided'}), 400

    # Trigger collection for each PR
    db = get_db_session()
    service = QueueService(db)

    results = []
    for num in pr_numbers:
        result = service.trigger_collection(num, repo_owner, repo_name, force)
        results.append({
            'pr_number': num,
            'status': result.get('status'),
            'message': result.get('message')
        })

    # Return summary
    total = len(results)
    created = sum(1 for r in results if r['status'] == 'created')
    reset = sum(1 for r in results if r['status'] == 'reset')
    skipped = sum(1 for r in results if r['status'] == 'skipped')

    return jsonify({
        'status': 'success',
        'total': total,
        'created': created,
        'reset': reset,
        'skipped': skipped,
        'results': results
    })


@bp.route('/reset-failed', methods=['POST'])
def reset_failed():
    """Reset all failed items to pending."""
    db = get_db_session()
    service = QueueService(db)
    result = service.reset_failed()

    return jsonify(result)


@bp.route('/reset-completed', methods=['POST'])
def reset_completed():
    """Reset all completed items to pending for re-collection."""
    db = get_db_session()
    service = QueueService(db)
    result = service.reset_completed()

    return jsonify(result)


@bp.route('/collect-new-prs', methods=['POST'])
def collect_new_prs():
    """Collect new PRs from GitHub (from last PR date to today)."""
    db = get_db_session()
    service = QueueService(db)
    result = service.collect_new_prs()

    return jsonify(result)


@bp.route('/validate-pr/<int:pr_number>', methods=['GET'])
def validate_pr(pr_number):
    """Validate that we have the latest test runs for a PR."""
    # Get optional repo owner and name from query parameters
    repo_owner = request.args.get('repo_owner')
    repo_name = request.args.get('repo_name')

    db = get_db_session()
    service = QueueService(db)
    result = service.validate_pr(pr_number, repo_owner, repo_name)

    return jsonify(result)
