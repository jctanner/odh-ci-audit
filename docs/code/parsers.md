# Parsers

## Overview

Parsers for Prow artifacts and test results.

## JUnit XML Parser

```python
import xml.etree.ElementTree as ET

def parse_junit_xml(xml_content):
    """Parse JUnit XML to extract test cases."""
    root = ET.fromstring(xml_content)

    test_cases = []
    for testsuite in root.findall('.//testsuite'):
        suite_name = testsuite.get('name')

        for testcase in testsuite.findall('.//testcase'):
            case = {
                'test_suite': suite_name,
                'test_name': testcase.get('name'),
                'classname': testcase.get('classname'),
                'duration_seconds': float(testcase.get('time', 0)),
                'status': 'passed'
            }

            # Check for failure
            failure = testcase.find('failure')
            if failure is not None:
                case['status'] = 'failed'
                case['failure_message'] = failure.get('message', '')
                case['failure_type'] = failure.get('type', '')
                case['stacktrace'] = failure.text or ''

            # Check for skipped
            if testcase.find('skipped') is not None:
                case['status'] = 'skipped'

            test_cases.append(case)

    return test_cases
```

## Prow JSON Parser

```python
import json

def parse_started_json(content):
    """Parse started.json artifact."""
    data = json.loads(content)
    return {
        'timestamp': data.get('timestamp'),
        'pull': data.get('pull'),
        'repos': data.get('repos', {}),
        'repo_version': data.get('repo-version')
    }

def parse_finished_json(content):
    """Parse finished.json artifact."""
    data = json.loads(content)
    return {
        'timestamp': data.get('timestamp'),
        'passed': data.get('passed'),
        'result': data.get('result'),
        'revision': data.get('revision')
    }

def parse_prowjob_json(content):
    """Parse prowjob.json artifact."""
    return json.loads(content)
```

## Build Log Parser

```python
import re

ERROR_PATTERNS = [
    r'Error:.*',
    r'FAIL:.*',
    r'panic:.*',
    r'FATAL:.*',
]

def extract_errors_from_log(log_content):
    """Extract error lines from build log."""
    errors = []

    for line in log_content.split('\n'):
        for pattern in ERROR_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                errors.append(line.strip())
                break

    return errors
```

## Related

- [Artifact Structure](../prow/artifacts.md)
- [API Reference](../api/collectors.md)
