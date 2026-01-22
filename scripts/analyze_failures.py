#!/usr/bin/env python3
"""Analyze CI test failure patterns and trends."""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from sqlalchemy import func, case, extract, desc
from sqlalchemy.orm import Session

from ci_audit.config import Config
from ci_audit.database.models import create_database, get_session, TestRun, TestCase, PullRequest


def analyze_job_type_failures(session: Session):
    """Analyze failure rates by job type."""
    print("=" * 80)
    print("FAILURE ANALYSIS BY JOB TYPE")
    print("=" * 80)
    print()

    # Extract job type suffix (last part after final dash)
    job_type = func.regexp_replace(TestRun.job_name, '.*-', '')

    results = (
        session.query(
            job_type.label('job_type'),
            func.count(func.distinct(TestRun.build_id)).label('total_runs'),
            func.count(func.distinct(
                case((TestRun.passed == False, TestRun.build_id))
            )).label('failed_runs'),
            func.round(
                100.0 * func.count(func.distinct(
                    case((TestRun.passed == False, TestRun.build_id))
                )) / func.count(func.distinct(TestRun.build_id)),
                1
            ).label('failure_rate')
        )
        .group_by(job_type)
        .order_by(
            desc(func.round(
                100.0 * func.count(func.distinct(
                    case((TestRun.passed == False, TestRun.build_id))
                )) / func.count(func.distinct(TestRun.build_id)),
                1
            )),
            desc(func.count(func.distinct(TestRun.build_id)))
        )
        .all()
    )

    print(f"{'Job Type':<15} {'Total Runs':>12} {'Failed Runs':>12} {'Failure Rate':>15}")
    print("-" * 80)

    for row in results:
        print(f"{row.job_type:<15} {row.total_runs:>12,} {row.failed_runs:>12,} {row.failure_rate:>14.1f}%")

    print()
    return results


def analyze_monthly_trends(session: Session):
    """Analyze failure rate trends over time by job type."""
    print("=" * 80)
    print("MONTHLY FAILURE TRENDS BY JOB TYPE")
    print("=" * 80)
    print()

    job_type = func.regexp_replace(TestRun.job_name, '.*-', '')
    month = func.date_trunc('month', TestRun.started_at)

    results = (
        session.query(
            job_type.label('job_type'),
            month.label('month'),
            func.count(func.distinct(TestRun.build_id)).label('total_runs'),
            func.count(func.distinct(
                case((TestRun.passed == False, TestRun.build_id))
            )).label('failed_runs'),
            func.round(
                100.0 * func.count(func.distinct(
                    case((TestRun.passed == False, TestRun.build_id))
                )) / func.count(func.distinct(TestRun.build_id)),
                1
            ).label('failure_rate')
        )
        .filter(TestRun.started_at != None)
        .group_by(job_type, month)
        .order_by(desc(month), job_type)
        .all()
    )

    # Group by month for better display
    current_month = None
    for row in results:
        month_str = row.month.strftime('%Y-%m') if row.month else 'Unknown'

        if current_month != month_str:
            if current_month is not None:
                print()
            current_month = month_str
            print(f"\n{month_str}")
            print(f"{'  Job Type':<17} {'Total':>8} {'Failed':>8} {'Rate':>8}")
            print("  " + "-" * 50)

        print(f"  {row.job_type:<15} {row.total_runs:>8,} {row.failed_runs:>8,} {row.failure_rate:>7.1f}%")

    print()
    return results


def analyze_e2e_test_failures(session: Session):
    """Deep dive into e2e test case failures."""
    print("=" * 80)
    print("E2E TEST CASE FAILURE ANALYSIS")
    print("=" * 80)
    print()

    # Get failure counts by test suite for e2e jobs only
    results = (
        session.query(
            TestCase.test_suite,
            func.count(TestCase.id).label('total_tests'),
            func.count(case((TestCase.status == 'failed', TestCase.id))).label('failed_tests'),
            func.round(
                100.0 * func.count(case((TestCase.status == 'failed', TestCase.id)))
                / func.count(TestCase.id),
                1
            ).label('failure_rate')
        )
        .join(TestRun, TestCase.run_id == TestRun.id)
        .filter(TestRun.job_name.like('%e2e'))
        .group_by(TestCase.test_suite)
        .order_by(desc(func.round(
                100.0 * func.count(case((TestCase.status == 'failed', TestCase.id)))
                / func.count(TestCase.id),
                1
            )))
        .limit(20)
        .all()
    )

    print(f"{'Test Suite':<40} {'Total Tests':>12} {'Failed':>12} {'Rate':>10}")
    print("-" * 80)

    for row in results:
        suite_name = row.test_suite if row.test_suite else '(no suite)'
        print(f"{suite_name:<40} {row.total_tests:>12,} {row.failed_tests:>12,} {row.failure_rate:>9.1f}%")

    print()
    return results


def analyze_top_failures(session: Session, limit=20):
    """Find most common test failures."""
    print("=" * 80)
    print(f"TOP {limit} MOST COMMON TEST FAILURES")
    print("=" * 80)
    print()

    results = (
        session.query(
            TestCase.test_suite,
            TestCase.test_name,
            func.count(TestCase.id).label('occurrences'),
            func.count(func.distinct(TestRun.pr_number)).label('unique_prs')
        )
        .join(TestRun, TestCase.run_id == TestRun.id)
        .filter(TestCase.status == 'failed')
        .group_by(TestCase.test_suite, TestCase.test_name)
        .order_by(desc(func.count(TestCase.id)))
        .limit(limit)
        .all()
    )

    print(f"{'#':<4} {'Occurrences':>12} {'PRs':>6} {'Test Suite':<25} {'Test Name':<40}")
    print("-" * 100)

    for i, row in enumerate(results, 1):
        suite = (row.test_suite or '(none)')[:24]
        name = (row.test_name or '(unknown)')[:39]
        print(f"{i:<4} {row.occurrences:>12,} {row.unique_prs:>6} {suite:<25} {name:<40}")

    print()
    return results


def generate_summary(session: Session):
    """Generate overall summary statistics."""
    print("=" * 80)
    print("OVERALL SUMMARY")
    print("=" * 80)
    print()

    # Total stats
    total_prs = session.query(func.count(PullRequest.id)).scalar()
    total_runs = session.query(func.count(TestRun.id)).scalar()
    total_tests = session.query(func.count(TestCase.id)).scalar()

    # Failure stats
    failed_runs = session.query(func.count(TestRun.id)).filter(TestRun.passed == False).scalar()
    failed_tests = session.query(func.count(TestCase.id)).filter(TestCase.status == 'failed').scalar()

    # Date range
    date_range = session.query(
        func.min(TestRun.started_at),
        func.max(TestRun.started_at)
    ).filter(TestRun.started_at != None).first()

    print(f"  Total PRs analyzed:        {total_prs:>12,}")
    print(f"  Total test runs:           {total_runs:>12,}")
    print(f"  Total test cases:          {total_tests:>12,}")
    print()
    print(f"  Failed test runs:          {failed_runs:>12,} ({100.0 * failed_runs / total_runs:.1f}%)")
    print(f"  Failed test cases:         {failed_tests:>12,} ({100.0 * failed_tests / total_tests:.1f}%)")
    print()

    if date_range[0] and date_range[1]:
        print(f"  Date range:                {date_range[0].strftime('%Y-%m-%d')} to {date_range[1].strftime('%Y-%m-%d')}")

    print()


@click.command()
@click.option('--config', default='config/config.yaml', help='Path to configuration file')
@click.option('--output', type=click.Path(), help='Write report to file instead of stdout')
def main(config, output):
    """Analyze CI test failure patterns and trends."""
    # Load configuration
    cfg = Config(config)

    # Connect to database
    engine = create_database(cfg.database_url, echo=False)
    session = get_session(engine)

    try:
        # Redirect output to file if specified
        original_stdout = None
        if output:
            import sys
            original_stdout = sys.stdout
            sys.stdout = open(output, 'w')

        print()
        print("*" * 80)
        print("CI AUDIT - FAILURE ANALYSIS REPORT")
        print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("*" * 80)
        print()

        # Run analyses
        generate_summary(session)
        analyze_job_type_failures(session)
        analyze_monthly_trends(session)
        analyze_e2e_test_failures(session)
        analyze_top_failures(session)

        print("*" * 80)
        print("END OF REPORT")
        print("*" * 80)

    finally:
        session.close()
        if output and original_stdout:
            sys.stdout.close()
            sys.stdout = original_stdout
            print(f"Report written to: {output}")


if __name__ == '__main__':
    main()
