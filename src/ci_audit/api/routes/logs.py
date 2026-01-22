"""API routes for log viewing."""

from flask import Blueprint, jsonify, Response

from ci_audit.api import get_db_session
from ci_audit.api.services.log_service import LogService

bp = Blueprint('logs', __name__, url_prefix='/api/logs')


@bp.route('/e2e/<build_id>', methods=['GET'])
def get_e2e_log(build_id):
    """Get e2e log content for a build."""
    db = get_db_session()
    service = LogService(db)
    content, error = service.get_e2e_log(build_id)

    if error:
        return jsonify({'error': error}), 404 if 'not found' in error.lower() else 500

    # Return as plain text with proper content type
    return Response(content, mimetype='text/plain')


@bp.route('/build/<build_id>', methods=['GET'])
def get_build_log(build_id):
    """Get build log content from database."""
    db = get_db_session()
    service = LogService(db)
    content, error = service.get_build_log(build_id)

    if error:
        return jsonify({'error': error}), 404 if 'not found' in error.lower() else 500

    # Return as plain text with proper content type
    return Response(content, mimetype='text/plain')
