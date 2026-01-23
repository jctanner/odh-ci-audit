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
    """Trigger collection for a PR."""
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

    # Trigger collection
    db = get_db_session()
    service = QueueService(db)
    result = service.trigger_collection(pr_number, repo_owner, repo_name, force)

    return jsonify(result)


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
