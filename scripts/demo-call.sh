#!/usr/bin/env bash
# Unit 1: compose health probe. Full demo call lands in Unit 3.
set -euo pipefail
BASE="${BASE_URL:-http://localhost:8080}"
MOCK="${MOCK_URL:-http://localhost:8001}"
curl -fsS "$BASE/healthz"; echo
curl -fsS "$MOCK/healthz"; echo
echo "stack healthy"
