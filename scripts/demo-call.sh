#!/usr/bin/env bash
# Unit 3: full demo call over WebSocket. Mock-only probe kept for CI speed.
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
BASE_URL="$BASE" python scripts/call_demo.py
