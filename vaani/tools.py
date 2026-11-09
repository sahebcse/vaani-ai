"""Agent tools. ABCs here; OpenSearch/Postgres backends land in Units 5-6."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDoc:
    text: str
    source: str


@dataclass(frozen=True)
class Account:
    user_id: str
    name: str
    balance_due: float
    due_date: str


@dataclass(frozen=True)
class Escalation:
    tenant: str
    reason: str
    transcript: str


class Retriever:
    """Policy lookup. Unit 4: keyword; Unit 5: OpenSearch hybrid."""

    async def retrieve(self, query: str, tenant: str) -> list[PolicyDoc]:
        raise NotImplementedError


class KeywordRetriever(Retriever):
    """Stopgap retriever (Unit 4); OpenSearch hybrid replaces it in Unit 5."""

    def __init__(self, docs: list[PolicyDoc]) -> None:
        self._docs = docs

    async def retrieve(self, query: str, tenant: str) -> list[PolicyDoc]:
        del tenant
        terms = {w.lower() for w in query.split() if len(w) > 2}
        scored = [(len(terms & {w.lower() for w in doc.text.split()}), doc) for doc in self._docs]
        ranked = sorted(
            [item for item in scored if item[0] > 0],
            key=lambda item: item[0],
            reverse=True,
        )
        if ranked:
            return [doc for _, doc in ranked[:2]]
        return list(self._docs[:1])


class AccountStore:
    async def lookup(self, user_id: str, tenant: str) -> Account | None:
        raise NotImplementedError


class InMemoryAccountStore(AccountStore):
    def __init__(self, accounts: dict[str, Account]) -> None:
        self._accounts = accounts

    async def lookup(self, user_id: str, tenant: str) -> Account | None:
        del tenant
        return self._accounts.get(user_id)


class EscalationSink:
    async def record(self, escalation: Escalation) -> None:
        raise NotImplementedError


class MemoryEscalationSink(EscalationSink):
    def __init__(self) -> None:
        self.records: list[Escalation] = []

    async def record(self, escalation: Escalation) -> None:
        self.records.append(escalation)
