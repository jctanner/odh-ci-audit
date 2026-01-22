# Data Models

## Overview

SQLAlchemy ORM models for CI audit data.

See [Database Schema](../setup/database-schema.md) for complete schema reference.

## Core Models

### PullRequest

```python
class PullRequest(Base):
    __tablename__ = 'pull_requests'

    pr_number = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    author = Column(String, nullable=False)
    created_at = Column(DateTime)
    merged_at = Column(DateTime)
    state = Column(String)
    labels = Column(JSONB)  # PostgreSQL JSONB for advanced querying

    # Relationships
    test_runs = relationship('TestRun', back_populates='pull_request')
    comments = relationship('PRComment', back_populates='pull_request')
```

### TestRun

```python
class TestRun(Base):
    __tablename__ = 'test_runs'

    id = Column(Integer, primary_key=True)
    build_id = Column(String, unique=True, nullable=False)
    pr_number = Column(Integer, ForeignKey('pull_requests.pr_number'))
    job_name = Column(String)
    result = Column(String)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    gcs_path = Column(String)
    prowjob_metadata = Column(JSONB)

    # Relationships
    pull_request = relationship('PullRequest', back_populates='test_runs')
    test_cases = relationship('TestCase', back_populates='test_run')
    build_log = relationship('BuildLog', uselist=False, back_populates='test_run')
```

### TestCase

```python
class TestCase(Base):
    __tablename__ = 'test_cases'

    id = Column(Integer, primary_key=True)
    test_run_id = Column(Integer, ForeignKey('test_runs.id'))
    test_suite = Column(String)
    test_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    duration_seconds = Column(Float)
    failure_message = Column(Text)
    stacktrace = Column(Text)
    failure_type = Column(String)  # Computed classification

    # Relationships
    test_run = relationship('TestRun', back_populates='test_cases')
```

## Usage Examples

### Querying

```python
from sqlalchemy.orm import sessionmaker
from ci_audit.database.models import PullRequest, TestRun, TestCase

Session = sessionmaker(bind=engine)
session = Session()

# Get PR with all test runs
pr = session.query(PullRequest).filter_by(pr_number=1234).first()
for run in pr.test_runs:
    print(f"{run.job_name}: {run.result}")

# Get failed test cases
failed = session.query(TestCase).filter_by(status='failed').all()

# Join query
results = session.query(TestCase, TestRun, PullRequest)\
    .join(TestRun)\
    .join(PullRequest)\
    .filter(TestCase.status == 'failed')\
    .all()
```

### Creating Records

```python
# Create PR
pr = PullRequest(
    pr_number=1234,
    title="Fix dashboard bug",
    author="developer",
    created_at=datetime.utcnow()
)
session.add(pr)

# Create test run
run = TestRun(
    build_id="abc123",
    pr_number=1234,
    job_name="e2e",
    result="SUCCESS"
)
session.add(run)
session.commit()
```

## Related

- [Database Schema](../setup/database-schema.md)
- [API Reference](../api/database.md)
