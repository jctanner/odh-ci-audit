#!/bin/bash
# Watch work queue progress in real-time

echo "CI Audit - Queue Monitor"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    clear
    echo "==========================================="
    echo "CI Audit Queue Status - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "==========================================="
    echo ""

    # Queue status
    echo "Work Queue:"
    podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -t -c \
        "SELECT
            LPAD(status, 10) || ': ' || LPAD(COUNT(*)::text, 4) ||
            '  (' || LPAD(ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1)::text, 5) || '%)'
         FROM work_queue
         GROUP BY status
         ORDER BY
            CASE status
                WHEN 'pending' THEN 1
                WHEN 'claimed' THEN 2
                WHEN 'completed' THEN 3
                WHEN 'failed' THEN 4
            END;"

    echo ""
    echo "Data Collected:"
    podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -t -c \
        "SELECT '  PRs: ' || LPAD(COUNT(*)::text, 5) FROM pull_requests UNION ALL
         SELECT '  Test Runs: ' || LPAD(COUNT(*)::text, 5) FROM test_runs UNION ALL
         SELECT '  Test Cases: ' || LPAD(COUNT(*)::text, 7) FROM test_cases UNION ALL
         SELECT '  Comments: ' || LPAD(COUNT(*)::text, 5) FROM pr_comments;"

    echo ""
    echo "Active Workers:"
    podman exec ci-audit-postgres psql -U ci_audit -d ci_audit -t -c \
        "SELECT '  ' || worker_id || ' (' || COUNT(*) || ' PRs): #' ||
                STRING_AGG(pr_number::text, ', #' ORDER BY pr_number)
         FROM work_queue
         WHERE status = 'claimed'
         GROUP BY worker_id
         ORDER BY worker_id;" 2>/dev/null || echo "  (no active workers)"

    echo ""
    echo "-------------------------------------------"
    echo "Refreshing every 5 seconds..."

    sleep 5
done
