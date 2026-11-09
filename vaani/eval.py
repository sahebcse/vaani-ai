"""Eval harness: dataset cases, judges, A/B prompt experiments."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from vaani.agent import AgentRunner


@dataclass(frozen=True)
class EvalCase:
    transcript: str
    language: str
    tenant: str
    expected_keywords: list[str]


@dataclass(frozen=True)
class ExperimentReport:
    name: str
    means: dict[str, float]
    winner: str
    runs: int


class Judge:
    def score(self, reply: str, case: EvalCase) -> float:
        raise NotImplementedError


class KeywordJudge(Judge):
    """F1 of expected keywords present in the reply. Deterministic, no LLM."""

    def score(self, reply: str, case: EvalCase) -> float:
        expected = {w.lower() for w in case.expected_keywords}
        if not expected:
            return 0.0
        words = {w.strip(".,!?;:").lower() for w in reply.split()}
        hits = expected & words
        if not hits:
            return 0.0
        precision = len(hits) / max(1, len(words))
        recall = len(hits) / len(expected)
        return 2 * precision * recall / (precision + recall)


async def run_experiment(
    name: str,
    prompts: list[str],
    dataset: list[EvalCase],
    answer: Callable[[str, EvalCase], Awaitable[str]],
    judge: Judge,
) -> ExperimentReport:
    """Run every prompt variant over the dataset; winner = highest mean."""
    if not dataset:
        raise ValueError("empty dataset")
    if len(prompts) < 2:
        raise ValueError("need at least two prompt variants")
    means: dict[str, float] = {}
    runs = 0
    for prompt in prompts:
        total = 0.0
        for case in dataset:
            reply = await answer(prompt, case)
            total += judge.score(reply, case)
            runs += 1
        means[prompt] = total / len(dataset)
    winner = max(prompts, key=lambda p: means[p])
    return ExperimentReport(name=name, means=means, winner=winner, runs=runs)


class AgentPromptRunner:
    """Drives a real AgentRunner; the variant becomes the reply style hint."""

    def __init__(self, agent: AgentRunner) -> None:
        self._agent = agent

    async def __call__(self, prompt: str, case: EvalCase) -> str:
        reply = await self._agent.run(case.transcript, case.language, case.tenant, style=prompt)
        return reply.text


def load_dataset(path: str) -> list[EvalCase]:
    """Read JSONL eval cases; missing file means no dataset (empty list)."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    cases: list[EvalCase] = []
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        cases.append(
            EvalCase(
                transcript=str(obj["transcript"]),
                language=str(obj.get("language", "en")),
                tenant=str(obj.get("tenant", "demo-nbfc")),
                expected_keywords=[str(k) for k in obj.get("expected_keywords", [])],
            )
        )
    return cases
