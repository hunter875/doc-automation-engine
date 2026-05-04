#!/bin/bash
set -e

API_URL="http://localhost:8000"
EMAIL="minhln8@gmail.com"
PASSWORD="Hunter87512@"
SHEET_ID="1vfWhL4ZFRiwlrhjEAlCemE9sPlNHvuxFiT_1hA5NDYI"

echo "=== E2E Ingestion Test ==="
echo "1. Login..."
LOGIN_RESP=$(curl -s -X POST "$API_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

TOKEN=$(echo "$LOGIN_RESP" | jq -r '.access_token')
TENANT_ID=$(echo "$LOGIN_RESP" | jq -r '.tenant_id')

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed: $LOGIN_RESP"
  exit 1
fi

echo "✅ Logged in | tenant_id=$TENANT_ID"

echo ""
echo "2. List templates..."
TEMPLATES=$(curl -s -X GET "$API_URL/api/v1/extraction/templates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID")

TEMPLATE_ID=$(echo "$TEMPLATES" | jq -r '.[0].id')
echo "✅ Using template_id=$TEMPLATE_ID"

echo ""
echo "3. Trigger async ingestion (KV30 mode)..."
INGEST_RESP=$(curl -s -X POST "$API_URL/api/v1/extraction/jobs/ingest/google-sheet" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d "{\"template_id\":\"$TEMPLATE_ID\",\"sheet_id\":\"$SHEET_ID\",\"mode\":\"kv30\"}")

TASK_ID=$(echo "$INGEST_RESP" | jq -r '.task_id')
echo "✅ Task enqueued | task_id=$TASK_ID"

echo ""
echo "4. Poll task status (max 60s)..."
for i in {1..20}; do
  sleep 3
  STATUS_RESP=$(curl -s -X GET "$API_URL/api/v1/extraction/jobs/ingest/google-sheet/$TASK_ID" \
    -H "Authorization: Bearer $TOKEN" \
    -H "X-Tenant-ID: $TENANT_ID")

  STATUS=$(echo "$STATUS_RESP" | jq -r '.status')
  echo "  [$i] status=$STATUS"

  if [ "$STATUS" == "completed" ]; then
    echo ""
    echo "✅ Task completed!"
    echo "$STATUS_RESP" | jq '.summary'

    # Check for resolver_debug in error case
    SUMMARY_STATUS=$(echo "$STATUS_RESP" | jq -r '.summary.status')
    if [ "$SUMMARY_STATUS" == "error" ]; then
      echo ""
      echo "⚠️ Ingestion returned error status. Resolver debug:"
      echo "$STATUS_RESP" | jq '.summary.resolver_debug'
    fi

    exit 0
  elif [ "$STATUS" == "failed" ]; then
    echo ""
    echo "❌ Task failed!"
    echo "$STATUS_RESP" | jq '.'
    exit 1
  fi
done

echo ""
echo "⏱️ Timeout waiting for task completion"
exit 1
