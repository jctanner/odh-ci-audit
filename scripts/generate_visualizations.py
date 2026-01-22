#!/usr/bin/env python3
"""
Generate time series visualizations for CI audit documentation.
"""

import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import psycopg2
from datetime import datetime

# Set style
sns.set_style('whitegrid')
plt.rcParams['figure.figsize'] = (14, 6)
plt.rcParams['font.size'] = 10

# Database connection parameters
DB_HOST = os.getenv('POSTGRES_HOST', 'localhost')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')
DB_USER = os.getenv('POSTGRES_USER', 'ci_audit')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'ci_audit_secure_password_123')
DB_NAME = os.getenv('POSTGRES_DB', 'ci_audit')

def get_connection():
    """Create a new database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )

# Output directory
OUTPUT_DIR = '/tmp/ci_audit_images'
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"Connecting to database: {DB_HOST}:{DB_PORT}/{DB_NAME}")
print(f"Output directory: {OUTPUT_DIR}")


def generate_weekly_failure_rate():
    """Generate weekly failure rate trend chart."""
    print("\n1. Generating weekly failure rate trend...")

    query = """
    SELECT
        DATE_TRUNC('week', started_at)::date as week_start,
        COUNT(*) as total_runs,
        SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
        SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) as failures,
        SUM(CASE WHEN result IN ('ABORTED', 'aborted', '') THEN 1 ELSE 0 END) as aborted,
        ROUND(100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*), 1) as failure_rate,
        ROUND(100.0 * SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*), 1) as success_rate,
        ROUND(100.0 * SUM(CASE WHEN result IN ('ABORTED', 'aborted', '') THEN 1 ELSE 0 END) / COUNT(*), 1) as abort_rate
    FROM test_runs
    WHERE started_at IS NOT NULL
    GROUP BY DATE_TRUNC('week', started_at)
    ORDER BY week_start;
    """

    df = pd.read_sql(query, get_connection(), parse_dates=['week_start'])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    # Plot 1: Stacked area chart
    ax1.fill_between(df['week_start'], 0, df['success_rate'],
                      label='Success', color='#2ecc71', alpha=0.7)
    ax1.fill_between(df['week_start'], df['success_rate'],
                      df['success_rate'] + df['failure_rate'],
                      label='Failure', color='#e74c3c', alpha=0.7)
    ax1.fill_between(df['week_start'], df['success_rate'] + df['failure_rate'], 100,
                      label='Aborted', color='#95a5a6', alpha=0.7)

    ax1.set_ylabel('Percentage (%)')
    ax1.set_title('Weekly Test Run Results (Stacked)', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, 100)

    # Plot 2: Line chart with volume
    ax2_twin = ax2.twinx()

    ax2.plot(df['week_start'], df['failure_rate'],
             label='Failure Rate', color='#e74c3c', marker='o', linewidth=2)
    ax2.plot(df['week_start'], df['success_rate'],
             label='Success Rate', color='#2ecc71', marker='s', linewidth=2)

    ax2_twin.bar(df['week_start'], df['total_runs'],
                 label='Total Runs', color='#3498db', alpha=0.3, width=5)

    ax2.set_xlabel('Week Starting')
    ax2.set_ylabel('Rate (%)')
    ax2_twin.set_ylabel('Total Runs')
    ax2.set_title('Weekly Failure & Success Rates', fontsize=14, fontweight='bold')
    ax2.legend(loc='upper left')
    ax2_twin.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/weekly_failure_rate.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/weekly_failure_rate.png")
    plt.close()


def generate_job_type_trends():
    """Generate failure rate trends by job type."""
    print("\n2. Generating job type failure trends...")

    query = """
    WITH categorized AS (
        SELECT
            DATE_TRUNC('week', started_at)::date as week_start,
            CASE
                WHEN job_name LIKE '%e2e-hypershift' THEN 'e2e-hypershift'
                WHEN job_name LIKE '%rhoai-e2e' THEN 'rhoai-e2e'
                WHEN job_name LIKE '%-operator-e2e' THEN 'e2e'
                WHEN job_name LIKE '%bundle%bundle' THEN 'bundle'
                WHEN job_name LIKE '%images' THEN 'images'
                ELSE 'other'
            END as job_type,
            result
        FROM test_runs
        WHERE started_at IS NOT NULL AND job_name IS NOT NULL
    )
    SELECT
        week_start,
        job_type,
        COUNT(*) as total_runs,
        ROUND(100.0 * SUM(CASE WHEN result = 'FAILURE' THEN 1 ELSE 0 END) / COUNT(*), 1) as failure_rate
    FROM categorized
    GROUP BY week_start, job_type
    HAVING COUNT(*) >= 5
    ORDER BY week_start, job_type;
    """

    df = pd.read_sql(query, get_connection())

    plt.figure(figsize=(14, 8))

    for job_type in ['e2e', 'e2e-hypershift', 'rhoai-e2e', 'bundle', 'images']:
        job_data = df[df['job_type'] == job_type]
        if len(job_data) > 0:
            plt.plot(job_data['week_start'], job_data['failure_rate'],
                    label=job_type, marker='o', linewidth=2, markersize=4)

    plt.xlabel('Week Starting')
    plt.ylabel('Failure Rate (%)')
    plt.title('Weekly Failure Rate by Job Type', fontsize=14, fontweight='bold')
    plt.legend(loc='best')
    plt.grid(True, alpha=0.3)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gca().xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/job_type_failure_trends.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/job_type_failure_trends.png")
    plt.close()


def generate_duration_trends():
    """Generate average duration trends over time."""
    print("\n3. Generating duration trends...")

    query = """
    SELECT
        DATE_TRUNC('week', started_at)::date as week_start,
        result,
        COUNT(*) as runs,
        ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 1) as avg_minutes
    FROM test_runs
    WHERE started_at IS NOT NULL
      AND finished_at IS NOT NULL
      AND result IN ('SUCCESS', 'FAILURE', 'ABORTED')
      AND EXTRACT(EPOCH FROM (finished_at - started_at)) > 0
      AND EXTRACT(EPOCH FROM (finished_at - started_at)) < 43200  -- Less than 12 hours
    GROUP BY DATE_TRUNC('week', started_at), result
    HAVING COUNT(*) >= 5
    ORDER BY week_start, result;
    """

    df = pd.read_sql(query, get_connection(), parse_dates=['week_start'])

    plt.figure(figsize=(14, 6))

    for result in ['SUCCESS', 'FAILURE', 'ABORTED']:
        result_data = df[df['result'] == result]
        if len(result_data) > 0:
            color = {'SUCCESS': '#2ecc71', 'FAILURE': '#e74c3c', 'ABORTED': '#95a5a6'}[result]
            plt.plot(result_data['week_start'], result_data['avg_minutes'],
                    label=result, marker='o', linewidth=2, color=color, markersize=4)

    plt.xlabel('Week Starting')
    plt.ylabel('Average Duration (minutes)')
    plt.title('Weekly Average Test Duration by Result', fontsize=14, fontweight='bold')
    plt.legend(loc='best')
    plt.grid(True, alpha=0.3)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gca().xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/duration_trends.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/duration_trends.png")
    plt.close()


def generate_pr_activity():
    """Generate PR creation activity over time."""
    print("\n4. Generating PR activity chart...")

    query = """
    SELECT
        DATE(created_at) as date,
        COUNT(*) as prs_created,
        COUNT(CASE WHEN merged_at IS NOT NULL THEN 1 END) as prs_merged
    FROM pull_requests
    GROUP BY DATE(created_at)
    HAVING COUNT(*) > 0
    ORDER BY date;
    """

    df = pd.read_sql(query, get_connection(), parse_dates=['date'])

    # Resample to weekly for cleaner visualization
    df_weekly = df.set_index('date').resample('W').sum().reset_index()

    fig, ax1 = plt.subplots(figsize=(14, 6))

    ax1.bar(df_weekly['date'], df_weekly['prs_created'],
            label='PRs Created', color='#3498db', alpha=0.7)
    ax1.bar(df_weekly['date'], df_weekly['prs_merged'],
            label='PRs Merged', color='#2ecc71', alpha=0.7)

    ax1.set_xlabel('Week')
    ax1.set_ylabel('Number of PRs')
    ax1.set_title('Weekly PR Activity', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/pr_activity.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/pr_activity.png")
    plt.close()


def generate_test_case_failure_trends():
    """Generate test case failure trends over time."""
    print("\n5. Generating test case failure trends...")

    query = """
    SELECT
        DATE_TRUNC('week', tr.started_at)::date as week_start,
        COUNT(*) as total_tests,
        SUM(CASE WHEN tc.status = 'failed' THEN 1 ELSE 0 END) as failures,
        ROUND(100.0 * SUM(CASE WHEN tc.status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 2) as failure_rate
    FROM test_cases tc
    JOIN test_runs tr ON tc.run_id = tr.id
    WHERE tr.started_at IS NOT NULL
    GROUP BY DATE_TRUNC('week', tr.started_at)
    ORDER BY week_start;
    """

    df = pd.read_sql(query, get_connection(), parse_dates=['week_start'])

    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax2 = ax1.twinx()

    ax1.bar(df['week_start'], df['total_tests'],
            label='Total Tests', color='#3498db', alpha=0.3, width=5)
    ax2.plot(df['week_start'], df['failure_rate'],
            label='Failure Rate', color='#e74c3c', marker='o', linewidth=2, markersize=5)

    ax1.set_xlabel('Week Starting')
    ax1.set_ylabel('Total Test Cases')
    ax2.set_ylabel('Failure Rate (%)', color='#e74c3c')
    ax1.set_title('Weekly Test Case Volume and Failure Rate', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left')
    ax2.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    ax2.tick_params(axis='y', labelcolor='#e74c3c')

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/test_case_failure_trends.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/test_case_failure_trends.png")
    plt.close()


def generate_time_cost_breakdown():
    """Generate time cost breakdown by result type."""
    print("\n6. Generating time cost breakdown...")

    query = """
    SELECT
        result,
        COUNT(*) as runs,
        ROUND(SUM(EXTRACT(EPOCH FROM (finished_at - started_at)) / 3600), 1) as total_hours,
        ROUND(AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) / 60), 1) as avg_minutes
    FROM test_runs
    WHERE started_at IS NOT NULL
        AND finished_at IS NOT NULL
        AND EXTRACT(EPOCH FROM (finished_at - started_at)) > 0
        AND EXTRACT(EPOCH FROM (finished_at - started_at)) < 43200
        AND result IN ('SUCCESS', 'FAILURE', 'ABORTED')
    GROUP BY result
    ORDER BY total_hours DESC;
    """

    df = pd.read_sql(query, get_connection())

    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Plot 1: Pie chart of time distribution
    colors = {'SUCCESS': '#2ecc71', 'FAILURE': '#e74c3c', 'ABORTED': '#95a5a6'}
    pie_colors = [colors.get(r, '#3498db') for r in df['result']]

    wedges, texts, autotexts = ax1.pie(df['total_hours'],
                                        labels=df['result'],
                                        autopct='%1.1f%%',
                                        colors=pie_colors,
                                        startangle=90,
                                        textprops={'fontsize': 12})

    # Make percentage text bold and white
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_weight('bold')
        autotext.set_fontsize(14)

    ax1.set_title('Total CI Time Distribution by Result\n(12,090 hours total)',
                  fontsize=14, fontweight='bold', pad=20)

    # Plot 2: Bar chart showing hours and average duration
    x = range(len(df))
    bars = ax2.bar(x, df['total_hours'], color=pie_colors, alpha=0.7, width=0.6)

    # Add value labels on bars
    for i, (idx, row) in enumerate(df.iterrows()):
        ax2.text(i, row['total_hours'] + 100, f"{row['total_hours']:,.0f}h\n({row['avg_minutes']:.1f} min avg)",
                ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax2.set_xticks(x)
    ax2.set_xticklabels(df['result'], fontsize=12)
    ax2.set_ylabel('Total Hours', fontsize=12)
    ax2.set_title('Total Time Spent by Result Type', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/time_cost_breakdown.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/time_cost_breakdown.png")
    plt.close()


def generate_time_cost_by_job_type():
    """Generate time cost breakdown by job type."""
    print("\n7. Generating time cost by job type...")

    query = """
    WITH categorized AS (
        SELECT
            CASE
                WHEN job_name LIKE '%e2e-hypershift' THEN 'e2e-hypershift'
                WHEN job_name LIKE '%rhoai-e2e' THEN 'rhoai-e2e'
                WHEN job_name LIKE '%-operator-e2e' THEN 'e2e'
                WHEN job_name LIKE '%bundle%bundle' THEN 'bundle'
                WHEN job_name LIKE '%images' THEN 'images'
                WHEN job_name LIKE '%image-mirror%' THEN 'image-mirror'
                ELSE 'other'
            END as job_type,
            result,
            EXTRACT(EPOCH FROM (finished_at - started_at)) / 3600 as hours
        FROM test_runs
        WHERE started_at IS NOT NULL
            AND finished_at IS NOT NULL
            AND EXTRACT(EPOCH FROM (finished_at - started_at)) > 0
            AND EXTRACT(EPOCH FROM (finished_at - started_at)) < 43200
    )
    SELECT
        job_type,
        ROUND(SUM(CASE WHEN result = 'SUCCESS' THEN hours ELSE 0 END), 1) as success_hours,
        ROUND(SUM(CASE WHEN result = 'FAILURE' THEN hours ELSE 0 END), 1) as failure_hours,
        ROUND(SUM(CASE WHEN result = 'ABORTED' THEN hours ELSE 0 END), 1) as aborted_hours,
        ROUND(SUM(hours), 1) as total_hours
    FROM categorized
    GROUP BY job_type
    ORDER BY total_hours DESC;
    """

    df = pd.read_sql(query, get_connection())

    fig, ax = plt.subplots(figsize=(14, 8))

    # Stacked horizontal bar chart
    x = range(len(df))

    p1 = ax.barh(x, df['success_hours'], label='Success', color='#2ecc71', alpha=0.8)
    p2 = ax.barh(x, df['failure_hours'], left=df['success_hours'],
                 label='Failure', color='#e74c3c', alpha=0.8)
    p3 = ax.barh(x, df['aborted_hours'], left=df['success_hours'] + df['failure_hours'],
                 label='Aborted', color='#95a5a6', alpha=0.8)

    # Add percentage labels for failures on the bars
    for i, row in df.iterrows():
        if row['total_hours'] > 0:
            failure_pct = 100.0 * row['failure_hours'] / row['total_hours']
            if failure_pct > 5:  # Only show if significant
                ax.text(row['success_hours'] + row['failure_hours']/2, i,
                       f"{failure_pct:.1f}%",
                       ha='center', va='center', fontsize=10,
                       fontweight='bold', color='white')

    # Add total hours at end of each bar
    for i, row in df.iterrows():
        ax.text(row['total_hours'] + 100, i, f"{row['total_hours']:,.0f}h",
               ha='left', va='center', fontsize=10, fontweight='bold')

    ax.set_yticks(x)
    ax.set_yticklabels(df['job_type'], fontsize=11)
    ax.set_xlabel('Total Hours', fontsize=12)
    ax.set_title('Time Cost by Job Type (Success vs Failure vs Aborted)',
                fontsize=14, fontweight='bold')
    ax.legend(loc='lower right', fontsize=11)
    ax.grid(True, alpha=0.3, axis='x')

    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/time_cost_by_job_type.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/time_cost_by_job_type.png")
    plt.close()


def generate_pr_run_distribution():
    """Generate distribution of runs per PR."""
    print("\n8. Generating PR run distribution...")

    query = """
    WITH pr_run_counts AS (
        SELECT
            pr_number,
            COUNT(*) as total_runs
        FROM test_runs
        GROUP BY pr_number
    )
    SELECT
        CASE
            WHEN total_runs <= 5 THEN '1-5 runs'
            WHEN total_runs <= 10 THEN '6-10 runs'
            WHEN total_runs <= 20 THEN '11-20 runs'
            WHEN total_runs <= 30 THEN '21-30 runs'
            WHEN total_runs <= 50 THEN '31-50 runs'
            ELSE '51+ runs'
        END as run_bucket,
        COUNT(*) as prs,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct_of_prs,
        MIN(total_runs) as min_runs
    FROM pr_run_counts
    GROUP BY run_bucket
    ORDER BY min_runs;
    """

    df = pd.read_sql(query, get_connection())

    fig, ax = plt.subplots(figsize=(12, 7))

    # Bar chart with color gradient
    colors = ['#2ecc71', '#3498db', '#f39c12', '#e67e22', '#e74c3c', '#c0392b']
    bars = ax.bar(range(len(df)), df['prs'], color=colors, alpha=0.8, width=0.6)

    # Add value labels on bars
    for i, row in df.iterrows():
        ax.text(i, row['prs'] + 3, f"{row['prs']} PRs\n({row['pct_of_prs']}%)",
               ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(df['run_bucket'], fontsize=11)
    ax.set_ylabel('Number of PRs', fontsize=12)
    ax.set_xlabel('Test Runs Required', fontsize=12)
    ax.set_title('Distribution of Test Runs Per PR\n(Only 24.9% pass with 1-5 runs, 11.7% need 51+ runs)',
                fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/pr_run_distribution.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/pr_run_distribution.png")
    plt.close()


def generate_time_of_day_success_rate():
    """Generate success rate by time of day."""
    print("\n9. Generating time of day success rate...")

    query = """
    SELECT
        EXTRACT(HOUR FROM started_at)::int as hour_utc,
        COUNT(*) as total_runs,
        SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
        ROUND(100.0 * SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*), 1) as success_rate
    FROM test_runs
    WHERE started_at IS NOT NULL
        AND result IN ('SUCCESS', 'FAILURE', 'ABORTED')
    GROUP BY EXTRACT(HOUR FROM started_at)
    ORDER BY hour_utc;
    """

    df = pd.read_sql(query, get_connection())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    # Plot 1: Success rate line
    ax1.plot(df['hour_utc'], df['success_rate'], marker='o', linewidth=2.5,
            color='#3498db', markersize=6)
    ax1.axhline(y=df['success_rate'].mean(), color='#e74c3c', linestyle='--',
               linewidth=2, alpha=0.7, label=f"Average: {df['success_rate'].mean():.1f}%")
    ax1.fill_between(df['hour_utc'], df['success_rate'], alpha=0.3, color='#3498db')

    # Highlight best and worst hours
    best_hour = df.loc[df['success_rate'].idxmax(), 'hour_utc']
    worst_hour = df.loc[df['success_rate'].idxmin(), 'hour_utc']
    ax1.scatter([best_hour], [df.loc[df['success_rate'].idxmax(), 'success_rate']],
               color='#2ecc71', s=200, zorder=5, label=f'Best: {best_hour}:00 UTC')
    ax1.scatter([worst_hour], [df.loc[df['success_rate'].idxmin(), 'success_rate']],
               color='#e74c3c', s=200, zorder=5, label=f'Worst: {worst_hour}:00 UTC')

    ax1.set_ylabel('Success Rate (%)', fontsize=12)
    ax1.set_title('Success Rate by Hour of Day (UTC)\n21% variance between best (5 AM) and worst (9 PM)',
                 fontsize=14, fontweight='bold')
    ax1.legend(loc='lower left', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(45, 75)

    # Plot 2: Test volume
    ax2.bar(df['hour_utc'], df['total_runs'], color='#95a5a6', alpha=0.6)
    ax2.set_xlabel('Hour (UTC)', fontsize=12)
    ax2.set_ylabel('Test Volume', fontsize=12)
    ax2.set_title('Test Volume by Hour', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')

    ax2.set_xticks(range(0, 24, 2))
    ax2.set_xticklabels([f'{h}:00' for h in range(0, 24, 2)])

    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/time_of_day_success_rate.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/time_of_day_success_rate.png")
    plt.close()


def generate_time_to_first_success():
    """Generate time to first success distribution."""
    print("\n10. Generating time to first success distribution...")

    query = """
    WITH pr_timeline AS (
        SELECT
            pr_number,
            MIN(started_at) as first_run,
            MIN(CASE WHEN result = 'SUCCESS' THEN started_at END) as first_success,
            EXTRACT(EPOCH FROM (MIN(CASE WHEN result = 'SUCCESS' THEN started_at END) - MIN(started_at))) / 3600 as hours_to_success
        FROM test_runs
        WHERE started_at IS NOT NULL
        GROUP BY pr_number
        HAVING SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) > 0
    ),
    bucketed AS (
        SELECT
            CASE
                WHEN hours_to_success = 0 THEN 'First run success'
                WHEN hours_to_success < 1 THEN 'Under 1 hour'
                WHEN hours_to_success < 6 THEN '1-6 hours'
                WHEN hours_to_success < 24 THEN '6-24 hours'
                WHEN hours_to_success < 72 THEN '1-3 days'
                WHEN hours_to_success < 168 THEN '3-7 days'
                ELSE '7+ days'
            END as time_bucket,
            hours_to_success,
            CASE
                WHEN hours_to_success = 0 THEN 1
                WHEN hours_to_success < 1 THEN 2
                WHEN hours_to_success < 6 THEN 3
                WHEN hours_to_success < 24 THEN 4
                WHEN hours_to_success < 72 THEN 5
                WHEN hours_to_success < 168 THEN 6
                ELSE 7
            END as sort_order
        FROM pr_timeline
    )
    SELECT
        time_bucket,
        COUNT(*) as prs,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct_of_prs,
        MIN(sort_order) as sort_order
    FROM bucketed
    GROUP BY time_bucket
    ORDER BY sort_order;
    """

    df = pd.read_sql(query, get_connection())

    fig, ax = plt.subplots(figsize=(12, 7))

    # Create color scale from green to red
    colors = ['#2ecc71', '#27ae60', '#f39c12', '#e67e22', '#e74c3c', '#c0392b', '#8b0000'][:len(df)]

    bars = ax.bar(range(len(df)), df['prs'], color=colors, alpha=0.8, width=0.6)

    # Add value labels on bars
    for i, row in df.iterrows():
        ax.text(i, row['prs'] + 10, f"{row['prs']} PRs\n({row['pct_of_prs']}%)",
               ha='center', va='bottom', fontsize=10, fontweight='bold')

    # Add cumulative percentage line
    cumulative_pct = df['pct_of_prs'].cumsum()
    ax2 = ax.twinx()
    ax2.plot(range(len(df)), cumulative_pct, color='#34495e', marker='D',
            linewidth=2.5, markersize=8, label='Cumulative %')
    ax2.axhline(y=97.4, color='#e74c3c', linestyle='--', linewidth=2, alpha=0.7)
    ax2.text(len(df)-1, 97.4, '97.4% within 1 hour',
            ha='right', va='bottom', fontsize=10, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(df['time_bucket'], rotation=15, ha='right', fontsize=11)
    ax.set_ylabel('Number of PRs', fontsize=12)
    ax2.set_ylabel('Cumulative Percentage', fontsize=12)
    ax.set_xlabel('Time to First Success', fontsize=12)
    ax.set_title('Time to First Successful Test Run\n(70% succeed on first try, 97.4% within 1 hour)',
                fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')
    ax2.legend(loc='upper left', fontsize=10)

    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/time_to_first_success.png', dpi=300, bbox_inches='tight')
    print(f"   Saved: {OUTPUT_DIR}/time_to_first_success.png")
    plt.close()


def main():
    """Generate all visualizations."""
    print("="*60)
    print("Generating Time Series Visualizations")
    print("="*60)

    try:
        generate_weekly_failure_rate()
        generate_job_type_trends()
        generate_duration_trends()
        generate_pr_activity()
        generate_test_case_failure_trends()
        generate_time_cost_breakdown()
        generate_time_cost_by_job_type()
        generate_pr_run_distribution()
        generate_time_of_day_success_rate()
        generate_time_to_first_success()

        print("\n" + "="*60)
        print("All visualizations generated successfully!")
        print(f"Output directory: {OUTPUT_DIR}")
        print("="*60)

    except Exception as e:
        print(f"\nError generating visualizations: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
