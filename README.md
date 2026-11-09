# Vaani — multilingual voice-AI agent for NBFC collections & support

Hindi + English voice agent (Sarvam AI, mocked locally) for collections and
support calls: audio in → transcript → LangGraph agent with RAG policy lookup
→ spoken reply, with evals, multi-tenancy, and full local reproducibility.

Full build order, gates, and keyword ledger: [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md).

## Quickstart

```bash
docker compose up --build -d
./scripts/demo-call.sh   # health probe in Unit 1; full demo call from Unit 3
```

Local dev (no Docker for unit tests):

```bash
python -m venv .venv && .\.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && ruff format --check . && mypy vaani mock-sarvam && pytest
```

## Units (each one commit, each green before the next)

- [x] Unit 1 (v0.1): scaffolding, domain models & Docker infra
- [x] Unit 2 (v0.2): speech provider abstraction + Mock Sarvam
- [x] Unit 3 (v0.3): WebSocket call loop
- [ ] Unit 4 (v0.4): LangGraph agent + tools
- [x] Unit 5 (v0.5): RAG (LangChain + OpenSearch)
- [ ] Unit 6 (v0.6): multi-tenancy, auth & admin REST APIs
- [ ] Unit 7 (v0.7): background jobs, eval harness & feedback loops
- [x] Unit 8 (v0.8): ops console, observability, quality gates
- [x] Unit 9 (v0.9): CDC analytics + chaos tests
- [ ] Unit 10 (v1.0): Terraform, load validation & polish
