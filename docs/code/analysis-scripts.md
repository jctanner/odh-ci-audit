# Analysis Scripts

## Overview

Python scripts for analyzing CI audit data.

## Duration Analysis

See [Duration Code](../analysis/duration/code.md) for complete script.

```bash
python3 scripts/analyze_duration.py
```

## Failure Analysis

See [Failure Code](../analysis/failures/code.md) for complete script.

```bash
python3 scripts/analyze_failures.py
```

## Flake Detection

```python
#!/usr/bin/env python3
"""Identify flaky tests."""

from sqlalchemy import create_engine
import pandas as pd

engine = create_engine('postgresql://ci_audit:password@localhost/ci_audit')

query = """
    SELECT test_name,
           SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes,
           SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
    FROM test_cases
    GROUP BY test_name
    HAVING SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) > 0
       AND SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
"""

df = pd.read_sql(query, engine)
df['flake_rate'] = 100.0 * df['failures'] / (df['passes'] + df['failures'])
print(df.sort_values('flake_rate', ascending=False).head(20))
```

## Failure Classification

```python
#!/usr/bin/env python3
"""Classify failures by type."""

import re
from sqlalchemy import create_engine, text

# Pattern definitions from classification.md
PATTERNS = {...}

def classify_failure(message, stacktrace):
    # Classification logic
    ...

# Update database with classifications
engine = create_engine('postgresql://ci_audit:password@localhost/ci_audit')
with engine.connect() as conn:
    failures = conn.execute(text(
        "SELECT id, failure_message, stacktrace FROM test_cases WHERE status='failed'"
    ))

    for row in failures:
        ftype = classify_failure(row.failure_message, row.stacktrace)
        conn.execute(text(
            "UPDATE test_cases SET failure_type = :ftype WHERE id = :id"
        ), {'ftype': ftype, 'id': row.id})
```

## Visualization

```python
import matplotlib.pyplot as plt
import seaborn as sns

# Set style
sns.set_style('whitegrid')
plt.rcParams['figure.figsize'] = (12, 6)

# Generate plots
# See individual analysis pages for specific visualizations
```

## Related

- [SQL Query Library](queries.md)
- [Duration Analysis](../analysis/duration/code.md)
- [Failure Analysis](../analysis/failures/code.md)
