"""Service layer for log operations."""

from typing import Optional, Tuple, List, Dict
from pathlib import Path
import logging
import re
from sqlalchemy.orm import Session

from ci_audit.database.models import TestRun, BuildLog

logger = logging.getLogger(__name__)


class LogService:
    """Business logic for log retrieval."""

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_e2e_log(self, build_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get e2e log content for a build.

        Args:
            build_id: Unique build identifier

        Returns:
            Tuple of (log_content, error_message)
            If successful, returns (content, None)
            If error, returns (None, error_message)
        """
        # Get test run to find log path
        test_run = self.db.query(TestRun).filter(TestRun.build_id == build_id).first()

        if not test_run:
            return None, f"Test run not found: {build_id}"

        if not test_run.e2e_log_path:
            return None, f"No e2e log available for build {build_id}"

        # Validate path to prevent directory traversal
        log_path = Path(test_run.e2e_log_path)
        if not self._is_safe_path(log_path):
            logger.warning(f"Attempted access to unsafe path: {log_path}")
            return None, "Invalid log path"

        # Read log file
        try:
            if not log_path.exists():
                return None, f"Log file not found: {log_path}"

            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            return content, None

        except Exception as e:
            logger.error(f"Error reading e2e log {log_path}: {e}")
            return None, f"Error reading log file: {str(e)}"

    def get_build_log(self, build_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get build log content from database.

        Args:
            build_id: Unique build identifier

        Returns:
            Tuple of (log_content, error_message)
            If successful, returns (content, None)
            If error, returns (None, error_message)
        """
        # Query build log via TestRun (BuildLog doesn't have build_id, it has run_id)
        build_log = self.db.query(BuildLog).join(TestRun).filter(TestRun.build_id == build_id).first()

        if not build_log:
            return None, f"Build log not found: {build_id}"

        if not build_log.log_content:
            return None, f"Build log is empty for build {build_id}"

        return build_log.log_content, None

    def _is_safe_path(self, path: Path) -> bool:
        """
        Validate that path is safe to read (no directory traversal).

        Args:
            path: Path to validate

        Returns:
            True if path is safe, False otherwise
        """
        try:
            # Resolve to absolute path
            resolved = path.resolve()

            # Check that path starts with /logs (expected base directory)
            # This prevents directory traversal attacks
            logs_base = Path("/logs").resolve()
            return str(resolved).startswith(str(logs_base))

        except Exception as e:
            logger.warning(f"Error validating path {path}: {e}")
            return False

    def search_log(self, build_id: str, pattern: str, context_lines: int = 2) -> Tuple[List[Dict], Optional[str]]:
        """
        Search build log for a pattern (server-side grep).

        Args:
            build_id: Unique build identifier
            pattern: Regex pattern to search for
            context_lines: Number of context lines to include around matches

        Returns:
            Tuple of (matches, error_message)
            matches is a list of dicts with line_number, line, and context
        """
        # Get build log content
        content, error = self.get_build_log(build_id)
        if error:
            return [], error

        return self._search_content(content, pattern, context_lines), None

    def search_e2e_log(self, build_id: str, pattern: str, context_lines: int = 2) -> Tuple[List[Dict], Optional[str]]:
        """
        Search e2e log for a pattern (server-side grep).

        Args:
            build_id: Unique build identifier
            pattern: Regex pattern to search for
            context_lines: Number of context lines to include around matches

        Returns:
            Tuple of (matches, error_message)
            matches is a list of dicts with line_number, line, and context
        """
        # Get e2e log content
        content, error = self.get_e2e_log(build_id)
        if error:
            return [], error

        return self._search_content(content, pattern, context_lines), None

    def _search_content(self, content: str, pattern: str, context_lines: int) -> List[Dict]:
        """
        Search content for pattern and return matches with context.

        Args:
            content: Log content to search
            pattern: Regex pattern to search for
            context_lines: Number of context lines around matches

        Returns:
            List of match dicts with line_number, line, and optional context
        """
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            # Fall back to literal string match
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        lines = content.split('\n')
        matches = []

        for i, line in enumerate(lines):
            if regex.search(line):
                match = {
                    'line_number': i + 1,
                    'line': line
                }

                # Add context if requested
                if context_lines > 0:
                    context_before = []
                    context_after = []

                    # Get context before
                    for j in range(max(0, i - context_lines), i):
                        context_before.append({
                            'line_number': j + 1,
                            'line': lines[j]
                        })

                    # Get context after
                    for j in range(i + 1, min(len(lines), i + context_lines + 1)):
                        context_after.append({
                            'line_number': j + 1,
                            'line': lines[j]
                        })

                    if context_before:
                        match['context_before'] = context_before
                    if context_after:
                        match['context_after'] = context_after

                matches.append(match)

        return matches
