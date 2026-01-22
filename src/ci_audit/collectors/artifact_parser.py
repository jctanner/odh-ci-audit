"""Parsers for test artifacts (junit XML, JSON metadata)."""

import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional
from datetime import datetime


logger = logging.getLogger(__name__)


class JunitParser:
    """Parser for junit XML test results."""

    @staticmethod
    def parse(xml_content: bytes) -> List[Dict[str, Any]]:
        """Parse junit XML and extract test cases.

        Args:
            xml_content: Raw XML content

        Returns:
            List of test case dictionaries
        """
        test_cases = []

        try:
            root = ET.fromstring(xml_content)

            # Handle both <testsuites> and <testsuite> root elements
            if root.tag == "testsuites":
                testsuites = root.findall("testsuite")
            else:
                testsuites = [root]

            for testsuite in testsuites:
                suite_name = testsuite.get("name", "unknown")

                for testcase in testsuite.findall("testcase"):
                    tc = {
                        "test_suite": suite_name,
                        "test_name": testcase.get("name", ""),
                        "classname": testcase.get("classname", ""),
                        "duration_seconds": float(testcase.get("time", 0)),
                        "status": "passed",
                        "failure_message": None,
                        "failure_type": None,
                        "failure_stacktrace": None,
                        "system_out": None,
                        "system_err": None,
                    }

                    # Check for failure
                    failure = testcase.find("failure")
                    if failure is not None:
                        tc["status"] = "failed"
                        tc["failure_message"] = failure.get("message", "")
                        tc["failure_type"] = failure.get("type", "")
                        tc["failure_stacktrace"] = failure.text or ""

                    # Check for error
                    error = testcase.find("error")
                    if error is not None:
                        tc["status"] = "error"
                        tc["failure_message"] = error.get("message", "")
                        tc["failure_type"] = error.get("type", "")
                        tc["failure_stacktrace"] = error.text or ""

                    # Check for skipped
                    skipped = testcase.find("skipped")
                    if skipped is not None:
                        tc["status"] = "skipped"

                    # Get stdout/stderr
                    system_out = testcase.find("system-out")
                    if system_out is not None:
                        tc["system_out"] = system_out.text

                    system_err = testcase.find("system-err")
                    if system_err is not None:
                        tc["system_err"] = system_err.text

                    test_cases.append(tc)

        except ET.ParseError as e:
            logger.error(f"Failed to parse junit XML: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing junit XML: {e}")

        return test_cases


class ProwMetadataParser:
    """Parser for Prow metadata JSON files."""

    @staticmethod
    def parse_started(json_content: bytes) -> Optional[Dict[str, Any]]:
        """Parse started.json metadata.

        Args:
            json_content: Raw JSON content

        Returns:
            Dictionary with parsed metadata or None on error
        """
        try:
            data = json.loads(json_content)

            return {
                "timestamp": datetime.fromtimestamp(data.get("timestamp", 0)),
                "pull_request": data.get("pull"),
                "repos": data.get("repos", {}),
                "node_name": data.get("node"),
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse started.json: {e}")
            return None

    @staticmethod
    def parse_finished(json_content: bytes) -> Optional[Dict[str, Any]]:
        """Parse finished.json metadata.

        Args:
            json_content: Raw JSON content

        Returns:
            Dictionary with parsed metadata or None on error
        """
        try:
            data = json.loads(json_content)

            return {
                "timestamp": datetime.fromtimestamp(data.get("timestamp", 0)),
                "result": data.get("result", "UNKNOWN"),
                "passed": data.get("passed", False),
                "revision": data.get("revision"),
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse finished.json: {e}")
            return None

    @staticmethod
    def parse_prowjob(json_content: bytes) -> Optional[Dict[str, Any]]:
        """Parse prowjob.json metadata.

        Args:
            json_content: Raw JSON content

        Returns:
            Dictionary with parsed metadata or None on error
        """
        try:
            data = json.loads(json_content)

            # Extract key fields from prowjob spec
            spec = data.get("spec", {})
            status = data.get("status", {})

            return {
                "job": spec.get("job"),
                "type": spec.get("type"),
                "cluster": spec.get("cluster"),
                "namespace": spec.get("namespace"),
                "refs": spec.get("refs", {}),
                "state": status.get("state"),
                "build_id": status.get("build_id"),
                "url": status.get("url"),
                "full_metadata": data,  # Store complete prowjob for reference
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse prowjob.json: {e}")
            return None


class BuildLogParser:
    """Parser for build logs."""

    ERROR_PATTERNS = [
        "ERROR:",
        "FATAL:",
        "FAIL:",
        "panic:",
        "Error:",
        "Failed",
        "Exception:",
    ]

    @staticmethod
    def extract_error_lines(log_content: str, max_lines: int = 1000) -> List[str]:
        """Extract lines containing errors from build log.

        Args:
            log_content: Full build log content
            max_lines: Maximum number of error lines to extract

        Returns:
            List of error lines
        """
        error_lines = []

        for line in log_content.split('\n'):
            # Check if line contains any error pattern
            if any(pattern in line for pattern in BuildLogParser.ERROR_PATTERNS):
                error_lines.append(line)

                if len(error_lines) >= max_lines:
                    break

        return error_lines

    @staticmethod
    def parse(log_content: bytes) -> Dict[str, Any]:
        """Parse build log and extract useful information.

        Args:
            log_content: Raw log content

        Returns:
            Dictionary with parsed log data
        """
        try:
            log_text = log_content.decode('utf-8', errors='replace')

            return {
                "log_content": log_text,
                "log_size_bytes": len(log_content),
                "error_lines": BuildLogParser.extract_error_lines(log_text),
            }
        except Exception as e:
            logger.error(f"Failed to parse build log: {e}")
            return {
                "log_content": None,
                "log_size_bytes": len(log_content),
                "error_lines": [],
            }
