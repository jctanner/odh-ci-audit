"""API routes for log viewing."""

from flask import Blueprint, jsonify, Response, request

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


@bp.route('/build/<build_id>/search', methods=['GET'])
def search_build_log(build_id):
    """Search build log for a pattern (server-side grep)."""
    pattern = request.args.get('q') or request.args.get('pattern')
    context_lines = request.args.get('context', default=2, type=int)
    format_type = request.args.get('format', default='text')

    if not pattern:
        return jsonify({'error': 'Query parameter "q" or "pattern" is required'}), 400

    db = get_db_session()
    service = LogService(db)
    results, error = service.search_log(build_id, pattern, context_lines)

    if error:
        return jsonify({'error': error}), 404 if 'not found' in error.lower() else 500

    # Return as JSON or text based on format parameter
    if format_type == 'json':
        return jsonify({
            'build_id': build_id,
            'pattern': pattern,
            'match_count': len(results),
            'matches': results
        })
    else:
        # Return as plain text with context
        text_output = '\n'.join([
            f"Line {match['line_number']}: {match['line']}"
            for match in results
        ])
        return Response(text_output, mimetype='text/plain')


@bp.route('/e2e/<build_id>/search', methods=['GET'])
def search_e2e_log(build_id):
    """Search e2e log for a pattern (server-side grep)."""
    pattern = request.args.get('q') or request.args.get('pattern')
    context_lines = request.args.get('context', default=2, type=int)
    format_type = request.args.get('format', default='text')

    if not pattern:
        return jsonify({'error': 'Query parameter "q" or "pattern" is required'}), 400

    db = get_db_session()
    service = LogService(db)
    results, error = service.search_e2e_log(build_id, pattern, context_lines)

    if error:
        return jsonify({'error': error}), 404 if 'not found' in error.lower() else 500

    # Return as JSON or text based on format parameter
    if format_type == 'json':
        return jsonify({
            'build_id': build_id,
            'pattern': pattern,
            'match_count': len(results),
            'matches': results
        })
    else:
        # Return as plain text with context
        text_output = '\n'.join([
            f"Line {match['line_number']}: {match['line']}"
            for match in results
        ])
        return Response(text_output, mimetype='text/plain')
