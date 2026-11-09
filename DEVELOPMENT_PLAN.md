# Vaani — Development Plan

Multilingual voice-AI agent for NBFC collections & support (Hindi + English).
Built unit-by-unit like ThrottleNet/LiveRank: each Unit is one commit (`Unit N
(v0.N): ...`), a complete end-to-end deliverable, with docs in `README.md`.

## 0. Non-negotiable rules (same discipline as the other two repos)

1. **No resume claims before code exists.** A keyword enters the resume only
   after the unit that earns it is merged, tested, and green.
2. **100% line coverage, every unit.** `pytest --cov=vaani --cov-fail-under=100`
   on application code (excludes: `vaani/main.py` bootstrap, `vaani/config.py`,
   `if TYPE_CHECKING` blocks). New code without tests does not merge.
   Integration/e2e tests must pass but sit outside the coverage numerator.
3. **Everything runs locally with `docker compose up`.** No cloud, no paid API.
4. **Sarvam is mocked, swappably.** All Sarvam calls go through the
   `SpeechProvider` interface. Local dev uses `MockSarvamServer`; real Sarvam
   later = env-var change (`SARVAM_BASE_URL`, `SARVAM_API_KEY`), zero code change.

## 1. Stack (pinned in Unit 1, changed only by a dedicated commit)

| Layer | Choice |
|---|---|
| API | Python 3.12, FastAPI, WebSockets (`/v1/calls/stream`) |
| Agent | LangGraph orchestration, LangChain retrieval chains |
| Speech | Sarvam AI (ASR/TTS/Translate) behind `SpeechProvider`; mock locally |
| Retrieval | OpenSearch (hybrid lexical + kNN; fallback: pgvector — see §6) |
| State | Postgres 16 (call ledger), Redis 7 (session/audio windows) |
| Events | Kafka (KRaft, ThrottleNet-lite pattern), Debezium CDC in Unit 9 |
| Tests | pytest, pytest-asyncio, httpx (incl. WebSocket), respx for HTTP mocks |
| Quality | ruff, mypy (strict on `vaani/`), SonarQube in CI (Unit 8), pytest-cov 100 gate |
| Infra | Docker Compose (dev) → Terraform AWS in Unit 10 |
| CI | GitHub Actions: `backend` (lint, mypy, unit+100% gate), `contract` (mock-vs-shape), `e2e` (compose + demo call), `docker-build` |

## 2. Mock Sarvam design (no API access needed, ever, for dev)

`mock-sarvam/` — a tiny FastAPI service in Compose implementing Sarvam's REST
shapes (`/speech-to-text`, `/text-to-speech`, `/translate`), with:

- **Deterministic fixture map**: SHA-256 of incoming audio bytes → canned
  transcript (Hindi + English fixtures checked in under `fixtures/audio/`);
  unknown audio → a default Hindi fixture (never an error, keeps e2e stable).
- **Latency knobs**: env-configured p50/p99 delays so backpressure/retry tests
  are deterministic.
- **Contract tests** (`tests/contract/`): assert the mock's request/response
  shapes match Sarvam's documented API, so swapping to real Sarvam cannot
  silently break the app. If Sarvam's docs change, only the mock + contract
  tests change.

## 3. Local end-to-end run (works from Unit 3 onward, grows each unit)

```bash
docker compose up --build -d
./scripts/demo-call.sh   # streams fixtures/audio/hindi-collection.wav over
                         # /v1/calls/stream, prints transcript → agent reply
                         # → synthesized audio bytes + RAG citations + eval score
```

`demo-call.sh` asserts: (a) transcript matches the fixture's expected text,
(b) agent reply cites a policy doc, (c) response audio is non-empty,
(d) per-call eval score ≥ threshold. It is the same script CI's `e2e` job runs.

## 4. Units (each: goal → deliverable → tests → e2e proof → keywords earned)

### Unit 1 (v0.1): Scaffolding, domain models & Docker infra
Repo layout (`vaani/`, `mock-sarvam/`, `tests/{unit,contract,e2e}/`,
`fixtures/`, `scripts/`, `ops-console/` stub), `docker-compose.yml`
(postgres, redis, kafka, opensearch, mock-sarvam), ruff/mypy/pytest config
with the 100 gate, CI skeleton, README quickstart. Tests: config loading,
health endpoint. E2E: `compose up` + `/healthz` green.
*Earns: nothing yet (foundation — same as LiveRank Unit 1).*

### Unit 2 (v0.2): Speech provider abstraction + Mock Sarvam
`SpeechProvider` interface (transcribe/synthesize/translate), `SarvamProvider`
(HTTP client, retries, timeouts), `MockSarvamServer` with fixture map + latency
knobs. Tests: interface contract, retry/backoff paths, timeout→fallback,
fixture determinism (same bytes → same transcript). E2E: mock server standalone
round-trip via `scripts/demo-call.sh --mock-only`.
*Earns: **ASR, TTS, Translate** (all three flow through the mock end-to-end).*

### Unit 3 (v0.3): WebSocket call loop (audio in → audio out)
`/v1/calls/stream`: per-call session in Redis, audio frames → provider →
transcript → (echo policy for now) → provider TTS → audio frames back;
backpressure (bounded frame queue, slow-consumer drop with counter),
robust close/error paths. Tests: full loop with mocked provider, backpressure
drop, disconnect mid-call, malformed frames. E2E: `demo-call.sh` streams the
Hindi fixture and gets audio back.
*Earns: **WebSockets**, **robust error handling**.*

### Unit 4 (v0.4): LangGraph agent + tools (the brain)
Agent graph: understand → (policy lookup | ledger check | escalate) → respond;
tools: `policy_search` (stub backend — real retrieval lands in Unit 5),
`account_lookup` (Postgres), `escalate_to_human`. Multi-LLM routing
(`LLM orchestration across multiple LLMs` — primary + fallback models).
Tests: graph paths per intent, tool-call parsing, fallback-LLM on primary
failure, escalation policy. E2E: text-mode call (no audio) resolves a
balance query from seeded data.
*Earns: **LLM + LLMs** (one phrase, both literals), **LangGraph**,
**LLMs and agentic tools**.*

### Unit 5 (v0.5): RAG over policy docs (LangChain + OpenSearch)
Ingestion (`scripts/ingest-policies.py`: chunk → embed → OpenSearch hybrid
index), LangChain retrieval chain behind `policy_search`, citation pass-through
to the agent reply, measured retrieval latency. Tests: chunking, hybrid query
construction, citation integrity, empty-index fallback. E2E: demo-call reply
cites the seeded collections policy.
*Earns: **LangChain**, **RAG** (deepened), **tuning queries** (only if the
measured p95 retrieval-latency tuning is kept — otherwise this term stays
unclaimed), **data stores** (reinforced).*

### Unit 6 (v0.6): Multi-tenancy, auth & admin REST APIs
Tenant isolation (per-tenant voices, policies, escalation rules; row-level
tenant guard in Postgres), JWT auth + tenant RBAC on admin APIs
(`/v1/admin/...`: tenants, voices, prompts, calls). Tests: cross-tenant
leakage attempts, RBAC matrix, token expiry. E2E: two tenants, same audio,
different voices/policies in replies.
*Earns: **multi-tenant services**, **REST APIs** (plural), **authentication,
authorization**.*

### Unit 7 (v0.7): Background jobs, eval harness & feedback loops
`@Scheduled`-style workers (apscheduler): call-record archival, prompt A/B
**experimental design** runner (two prompt variants → scored → winner
promoted), thumbs-up/down **feedback loops** endpoint feeding the eval dataset,
nightly eval report. Tests: scheduler triggers, A/B scoring math, feedback
ingestion, dataset growth. E2E: run one A/B experiment end-to-end via admin
API and read the report.
*Earns: **background job patterns**, **experimental design**,
**feedback loops**, **Evaluations** (deepened).*

### Unit 8 (v0.8): Ops console (React) + observability + quality gates
Minimal containerized React console (live calls, transcripts, eval reports —
mirrors the ThrottleNet/LiveRank dashboards), Prometheus metrics
(call duration, ASR/TTS latency, agent tool success, eval scores) + Grafana
dashboard JSON, structured logging with trace IDs, SonarQube in CI
(= `static analysis`), Playwright e2e specs for the console.
*Earns: **static analysis**, **Playwright**, **Prometheus** (reinforced).*

### Unit 9 (v0.9): CDC analytics pipeline + chaos tests
Debezium → Kafka → warehouse tables for call records; analytics endpoints
(deflection rate, containment, eval trends). Chaos tests (Testcontainers):
kill mock-sarvam mid-call → provider fallback; Redis down → session recovery;
Kafka restart → no lost call records. Tests: connector config, chaos suite.
E2E: chaos run green in CI.
*Earns: **change data capture**, resilience story (no new JD literals —
same as LiveRank Unit 9).*

### Unit 10 (v1.0): Terraform, load validation & polish
Terraform AWS (ECS/Fargate, RDS, ElastiCache, MSK-or-self-hosted Kafka,
OpenSearch domain), `scripts/load-test.jmx` (sustained concurrent calls,
p99 audio-first-byte), README full docs per unit (same style as the other
repos), demo video script. Tests: `terraform validate` + plan in CI,
contract tests re-run.
*Earns: **Terraform**, **test automation frameworks** (contract + eval +
perf harness in CI). v1.0 tag.*

## 5. Keyword ledger (what this repo earns, in JD order)

`Terraform` [3] (U10), `test automation frameworks` [3] (U10),
`ASR/TTS/Translate` [2] (U2), `LLM` + `LLMs` [2] (U4), `LangChain` [2] (U5),
`LangGraph` [2] (U4), `LLMs and agentic tools` [2] (U4),
`experimental design` [2] (U7), `feedback loops` [2] (U7),
`WebSockets` [2] (U3), `multi-tenant services` [2] (U6), `REST APIs` [2] (U6),
`change data capture` [2] (U9), `tuning queries` [2] (U5, if measured),
`static analysis` [2] (U8), `Playwright` [1] (U8),
`authentication/authorization` [1] (U6). Reinforced (already on resume):
RAG, Evaluations, Prometheus, background job patterns, robust error handling.

Deliberately NOT pursued here: `C#`/`Rust`/`Django`/`Cassandra`/`MSSQL`
(wrong stack), `consensus`/`sharding`/`multi-region` (provided, not built),
`money movement`/`payment rails` (belongs in the PhonePe work bullet, not here).

## 6. Open decisions (default in parentheses)

1. OpenSearch (earns the term) vs pgvector (lighter, earns nothing).
   Default: OpenSearch; one-line fallback to pgvector in Unit 5.
2. Hindi-first (Sarvam strength, matches the NBFC story) vs English-first.
   Default: Hindi-first fixtures, English second.
3. Vision KYC-doc check: Phase 2 after v1.0, or cut entirely.
4. Coverage: 100 gate as specified above (stricter than the 80% elsewhere —
   sustainable only because units stay small; if a unit can't hit 100
   honestly, split the unit, don't lower the gate).

## 7. Resume landing (after v1.0 — or after Unit 7 for an interim bullet)

RideFlow is replaced by one 4-line Vaani entry (same verification loop as
before: compile → 4-line check → literal re-check → rescore). Skills additions
earned by the build, no deletions: `LangChain, LangGraph` (Data & AI),
`Terraform` (Cloud/DevOps), `WebSockets` (Concepts), `OpenSearch` (Data & AI).
