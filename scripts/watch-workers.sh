#!/bin/bash
# Watch all worker logs in one view with clean formatting

# Get container IDs mapped to names
declare -A CONTAINER_NAMES
for i in 1 2 3 4 5; do
    CID=$(podman ps --filter name=ci-audit-worker$i --format "{{.ID}}")
    CONTAINER_NAMES[$CID]="worker$i"
done

# Stream logs and replace container IDs with worker names
podman logs -f \
  --timestamps \
  --tail=20 \
  ci-audit-worker1 \
  ci-audit-worker2 \
  ci-audit-worker3 \
  ci-audit-worker4 \
  ci-audit-worker5 2>&1 | \
while IFS= read -r line; do
    # Extract container ID (first 12 chars)
    cid="${line:0:12}"
    # Get worker name
    worker="${CONTAINER_NAMES[$cid]}"
    if [ -n "$worker" ]; then
        # Replace container ID with worker name
        echo "[${worker}]${line:12}"
    else
        echo "$line"
    fi
done
