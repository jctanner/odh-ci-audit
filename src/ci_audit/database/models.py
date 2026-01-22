"""SQLAlchemy ORM models for CI audit database."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, Index, UniqueConstraint, create_engine
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import declarative_base, relationship, Session

Base = declarative_base()


class PullRequest(Base):
    """GitHub Pull Request metadata."""

    __tablename__ = "pull_requests"

    # Synthetic primary key for multi-repo support
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Repository identification
    repo_owner = Column(String(255), nullable=False)  # e.g., "opendatahub-io"
    repo_name = Column(String(255), nullable=False)   # e.g., "opendatahub-operator"
    pr_number = Column(Integer, nullable=False)       # PR number within the repo

    # PR metadata
    title = Column(Text, nullable=False)
    author = Column(String(255), nullable=False)
    state = Column(String(20), nullable=False)  # open, closed, merged
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime)
    merged_at = Column(DateTime)
    closed_at = Column(DateTime)
    base_ref = Column(String(255))  # usually 'main'
    head_ref = Column(String(255))
    head_sha = Column(String(40))
    labels = Column(JSONB)  # JSON array of label names
    is_draft = Column(Boolean)
    pr_metadata = Column(JSONB)  # JSON for additional fields
    last_collected_at = Column(DateTime)

    # Relationships
    test_runs = relationship("TestRun", back_populates="pull_request", cascade="all, delete-orphan")

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("repo_owner", "repo_name", "pr_number", name="uq_pr_repo_number"),
        Index("idx_pr_repo", "repo_owner", "repo_name"),
        Index("idx_pr_created", "created_at"),
        Index("idx_pr_state", "state"),
        Index("idx_pr_number", "pr_number"),
    )

    def __repr__(self):
        return f"<PullRequest(pr_number={self.pr_number}, title='{self.title[:50]}')>"


class TestRun(Base):
    """Prow test run execution."""

    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    build_id = Column(String(50), unique=True, nullable=False)  # Prow build ID
    pr_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False)  # FK to PullRequest.id
    pr_number = Column(Integer, nullable=False)  # Denormalized for convenience
    job_name = Column(String(255), nullable=False)
    started_at = Column(DateTime)  # Nullable - some builds lack started.json
    finished_at = Column(DateTime)  # Nullable - some builds lack finished.json
    duration_seconds = Column(Integer)
    result = Column(String(20))  # SUCCESS, FAILURE, ABORTED, PENDING
    passed = Column(Boolean)
    commit_sha = Column(String(40))
    gcs_path = Column(Text, nullable=False)  # Full path to artifacts in GCS
    repos = Column(JSONB)  # JSON of repos being tested
    node_name = Column(String(255))
    prowjob_metadata = Column(JSONB)  # JSON from prowjob.json
    e2e_log_path = Column(Text)  # Filesystem path to e2e test execution log
    diagnostic_summary = Column(JSONB)  # Extracted diagnostic info (fail-fast checks, warnings, etc.)
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    pull_request = relationship("PullRequest", back_populates="test_runs")
    test_cases = relationship("TestCase", back_populates="test_run", cascade="all, delete-orphan")
    build_log = relationship("BuildLog", back_populates="test_run", uselist=False, cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_run_pr_id", "pr_id"),
        Index("idx_run_pr_number", "pr_number"),
        Index("idx_run_result", "result"),
        Index("idx_run_started", "started_at"),
        Index("idx_run_build_id", "build_id"),
    )

    def __repr__(self):
        return f"<TestRun(build_id='{self.build_id}', pr_number={self.pr_number}, result='{self.result}')>"


class TestCase(Base):
    """Individual test case from junit XML."""

    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    test_suite = Column(String(255), nullable=False)  # e.g., "kserve", "dashboard"
    test_name = Column(Text, nullable=False)  # Full test name from junit
    classname = Column(String(255))  # Test class/file
    status = Column(String(20), nullable=False)  # passed, failed, skipped, error
    duration_seconds = Column(Float)
    failure_message = Column(Text)  # Error message if failed
    failure_type = Column(String(255))  # Exception type or failure category
    failure_stacktrace = Column(Text)  # Full stack trace
    system_out = Column(Text)  # stdout
    system_err = Column(Text)  # stderr

    # Relationships
    test_run = relationship("TestRun", back_populates="test_cases")

    # Indexes
    __table_args__ = (
        Index("idx_testcase_run", "run_id"),
        Index("idx_testcase_status", "status"),
        Index("idx_testcase_suite", "test_suite"),
        Index("idx_testcase_name", "test_name", mysql_length=255),
    )

    def __repr__(self):
        return f"<TestCase(test_suite='{self.test_suite}', test_name='{self.test_name[:30]}', status='{self.status}')>"


class BuildLog(Base):
    """Build logs stored separately due to size."""

    __tablename__ = "build_logs"

    run_id = Column(Integer, ForeignKey("test_runs.id", ondelete="CASCADE"), primary_key=True)
    log_content = Column(Text)  # Full build log
    log_size_bytes = Column(Integer)
    error_lines = Column(JSONB)  # JSON array of extracted error lines

    # Relationships
    test_run = relationship("TestRun", back_populates="build_log")

    def __repr__(self):
        return f"<BuildLog(run_id={self.run_id}, size={self.log_size_bytes})>"


class FailurePattern(Base):
    """Computed/cached analysis of failure patterns."""

    __tablename__ = "failure_patterns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pattern_hash = Column(String(64), unique=True, nullable=False)  # Hash of normalized failure signature
    pattern_type = Column(String(50), nullable=False)  # e.g., "timeout", "assertion", "panic"
    test_suite = Column(String(255))
    test_name_pattern = Column(Text)  # Regex or normalized name
    failure_signature = Column(Text, nullable=False)  # Normalized failure message
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    occurrence_count = Column(Integer, default=1)
    affected_prs = Column(JSONB)  # JSON array of PR numbers
    sample_run_id = Column(Integer)  # Reference to example failure
    root_cause_category = Column(String(50))  # Manual or ML-classified category
    root_cause_notes = Column(Text)

    # Indexes
    __table_args__ = (
        Index("idx_pattern_type", "pattern_type"),
        Index("idx_pattern_suite", "test_suite"),
        Index("idx_pattern_hash", "pattern_hash"),
    )

    def __repr__(self):
        return f"<FailurePattern(pattern_type='{self.pattern_type}', occurrences={self.occurrence_count})>"


class PRComment(Base):
    """Pull request comments (issue comments, review comments, and reviews)."""

    __tablename__ = "pr_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pr_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False)  # FK to PullRequest.id
    pr_number = Column(Integer, nullable=False)  # Denormalized for convenience
    comment_id = Column(BigInteger, unique=True, nullable=False)  # GitHub comment ID
    comment_type = Column(String(20), nullable=False)  # issue_comment, review_comment, review
    author = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime)
    body = Column(Text)  # Comment text
    review_state = Column(String(20))  # For reviews: APPROVED, CHANGES_REQUESTED, COMMENTED
    in_reply_to_id = Column(Integer)  # For threaded comments
    path = Column(String(500))  # File path for review comments
    line = Column(Integer)  # Line number for review comments
    commit_id = Column(String(40))  # Commit SHA for review comments
    comment_metadata = Column(JSONB)  # JSON for additional fields

    # Indexes
    __table_args__ = (
        Index("idx_comment_pr_id", "pr_id"),
        Index("idx_comment_pr_number", "pr_number"),
        Index("idx_comment_type", "comment_type"),
        Index("idx_comment_author", "author"),
        Index("idx_comment_created", "created_at"),
    )

    def __repr__(self):
        return f"<PRComment(pr_number={self.pr_number}, type='{self.comment_type}', author='{self.author}')>"


class WorkQueue(Base):
    """Work queue for parallel worker coordination."""

    __tablename__ = "work_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Repository and PR identification (no FK to allow queueing before PR exists in DB)
    repo_owner = Column(String(255), nullable=False)
    repo_name = Column(String(255), nullable=False)
    pr_number = Column(Integer, nullable=False)

    # Work tracking
    status = Column(String(20), nullable=False, default='pending')  # pending, claimed, completed, failed
    worker_id = Column(String(100))  # Container hostname/ID
    claimed_at = Column(DateTime)
    completed_at = Column(DateTime)
    attempt_count = Column(Integer, default=0)
    last_error = Column(Text)
    priority = Column(Integer, default=0)  # Higher = more important

    # Indexes
    __table_args__ = (
        UniqueConstraint("repo_owner", "repo_name", "pr_number", name="uq_workqueue_repo_pr"),
        Index("idx_workqueue_status", "status"),
        Index("idx_workqueue_repo", "repo_owner", "repo_name"),
        Index("idx_workqueue_pr", "pr_number"),
        Index("idx_workqueue_priority", "priority", "status"),
    )

    def __repr__(self):
        return f"<WorkQueue({self.repo_owner}/{self.repo_name}#{self.pr_number}, status='{self.status}', worker_id='{self.worker_id}')>"


class CollectionState(Base):
    """Track collection state for resumable operations."""

    __tablename__ = "collection_state"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<CollectionState(key='{self.key}', value='{self.value[:50]}')>"


def create_database(db_url: str, echo: bool = False):
    """Create PostgreSQL database and all tables.

    Args:
        db_url: PostgreSQL database URL
        echo: Whether to echo SQL statements

    Returns:
        SQLAlchemy engine
    """
    # Configure connection pooling for PostgreSQL
    engine = create_engine(
        db_url,
        echo=echo,
        poolclass=QueuePool,
        pool_size=10,  # Base pool size
        max_overflow=20,  # Allow 20 additional connections
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=3600,  # Recycle connections after 1 hour
    )

    Base.metadata.create_all(engine)
    return engine


def get_session(engine) -> Session:
    """Create a new database session.

    Args:
        engine: SQLAlchemy engine

    Returns:
        SQLAlchemy session
    """
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    return Session()
