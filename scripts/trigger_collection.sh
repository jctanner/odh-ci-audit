#!/bin/bash
#
# Trigger force collection for specific PRs via REST API
#
# Usage: ./trigger_collection.sh

API_URL="${API_URL:-http://localhost:5000}"

echo "Triggering force collection for PRs 3048 and 3104..."

response=$(curl -s -X POST "${API_URL}/api/queue/trigger" \
  -H "Content-Type: application/json" \
  -d '{
    "pr_number": "3048,3104",
    "repo_owner": "opendatahub-io",
    "repo_name": "opendatahub-operator",
    "force": true
  }')

# Pretty print response if jq is available, otherwise just echo
if command -v jq &> /dev/null; then
    echo "$response" | jq '.'
else
    echo "$response"
fi

echo ""
echo "Done!"
