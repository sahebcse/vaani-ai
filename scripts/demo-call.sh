#!/usr/bin/env bash
# Unit 9: ingest policies, run the demo call, then drain the CDC relay.
set -euo pipefail
OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
KAFKA="${VAANI_KAFKA_BOOTSTRAP_SERVERS:-localhost:29092}"
PGDSN="${VAANI_POSTGRES_DSN:-postgresql://vaani:vaani@localhost:5432/vaani}"
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
VAANI_KAFKA_BOOTSTRAP_SERVERS="$KAFKA" VAANI_POSTGRES_DSN="$PGDSN" \
  python scripts/relay-once.py --expect-min 1 --timeout-seconds 30
echo "e2e ok: call ran, relay drained, warehouse loaded"
