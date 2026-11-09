#!/usr/bin/env bash
# Unit 1: compose health probe. Unit 2: mock-only speech round-trip.
# Full demo call (WebSocket) lands in Unit 3.
set -euo pipefail
BASE="${BASE_URL:-http://localhost:8080}"
MOCK="${MOCK_URL:-http://localhost:8001}"
if [ "${1:-}" = "--mock-only" ]; then
  curl -fsS "$MOCK/healthz"; echo
  curl -fsS -X POST "$MOCK/text-to-speech" \
    -H 'Content-Type: application/json' \
    -d '{"text":"test","language":"hi"}' | head -c 120; echo
  echo "mock speech round-trip ok"
  exit 0
fi
curl -fsS "$BASE/healthz"; echo
curl -fsS "$MOCK/healthz"; echo
echo "stack healthy"
