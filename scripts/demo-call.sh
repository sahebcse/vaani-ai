#!/usr/bin/env bash
# Unit 5: ingest policies into OpenSearch, then run the full demo call.
set -euo pipefail
OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
if [ "${1:-}" = "--mock-only" ]; then
  MOCK="${MOCK_URL:-http://localhost:8001}"
  curl -fsS "$MOCK/healthz"; echo
  curl -fsS -X POST "$MOCK/text-to-speech" \
    -H 'Content-Type: application/json' \
    -d '{"text":"test","language":"hi"}' | head -c 120; echo
  echo "mock speech round-trip ok"
  exit 0
fi
OPENSEARCH_URL="$OPENSEARCH_URL" python scripts/ingest-policies.py
BASE_URL="$BASE_URL" python scripts/call_demo.py
