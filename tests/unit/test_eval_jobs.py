"""Unit tests for the eval harness and background jobs."""

from pathlib import Path

import pytest

from vaani.agent import AgentRunner
from vaani.eval import (
    AgentPromptRunner,
    EvalCase,
    Judge,
    KeywordJudge,
    load_dataset,
    run_experiment,
)
from vaani.jobs import Feedback, FeedbackStore, archive_calls, create_scheduler
from vaani.ledger import CallLog, CallRecord
from vaani.llm import MockResponder
from vaani.tools import InMemoryAccountStore, KeywordRetriever, MemoryEscalationSink, PolicyDoc


def agent() -> AgentRunner:
    return AgentRunner(
        MockResponder(),
        KeywordRetriever([PolicyDoc(text="loan payment policy", source="p.md")]),
        InMemoryAccountStore({}),
        MemoryEscalationSink(),
    )


def case(text: str, keywords: list[str]) -> EvalCase:
    return EvalCase(transcript=text, language="en", tenant="t1", expected_keywords=keywords)


async def fake_answer(prompt: str, case: EvalCase) -> str:
    del prompt
    return "loan payment policy words words words"


async def test_judge_perfect_and_zero() -> None:
    with pytest.raises(NotImplementedError):
        Judge().score("x", case("x", ["y"]))

    judge = KeywordJudge()
    assert judge.score("loan payment", case("x", ["loan", "payment"])) == 1.0
    assert judge.score("nothing relevant here", case("x", ["loan"])) == 0.0
    assert judge.score("anything", case("x", [])) == 0.0


async def test_experiment_picks_highest_mean() -> None:
    dataset = [case("loan?", ["loan"]), case("policy?", ["policy"])]
    report = await run_experiment(
        "exp", ["concise", "detailed"], dataset, fake_answer, KeywordJudge()
    )
    assert report.name == "exp"
    assert report.runs == 4
    assert report.winner == "concise"  # tie -> first wins
    assert report.means["concise"] == report.means["detailed"]


async def test_experiment_rejects_empty_dataset() -> None:
    with pytest.raises(ValueError, match="empty dataset"):
        await run_experiment("e", ["a", "b"], [], fake_answer, KeywordJudge())


async def test_experiment_rejects_single_prompt() -> None:
    with pytest.raises(ValueError, match="at least two"):
        await run_experiment("e", ["only"], [case("x", ["y"])], fake_answer, KeywordJudge())


async def test_agent_prompt_runner_delegates() -> None:
    runner = AgentPromptRunner(agent())
    out = await runner("concise", case("loan?", ["loan"]))
    assert "loan payment policy" in out


def test_load_dataset_reads_jsonl() -> None:
    path = Path(__file__).resolve().parents[2] / "fixtures" / "eval" / "dataset.jsonl"
    cases = load_dataset(str(path))
    assert len(cases) == 3
    assert cases[0].expected_keywords == ["किस्त", "7"]


def test_load_dataset_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_dataset(str(tmp_path / "nope.jsonl")) == []


def test_load_dataset_skips_blanks(tmp_path: Path) -> None:
    path = tmp_path / "d.jsonl"
    path.write_text(
        '{"transcript": "hi", "language": "en", "tenant": "t", "expected_keywords": ["a"]}\n\n',
        encoding="utf-8",
    )
    cases = load_dataset(str(path))
    assert len(cases) == 1
    assert cases[0].language == "en"


def test_feedback_store_roundtrip() -> None:
    store = FeedbackStore()
    assert store.count() == 0
    store.record(Feedback(call_id="c", tenant="t", helpful=True, note="good"))
    store.record(Feedback(call_id="d", tenant="t", helpful=False))
    assert store.count() == 2
    recent = store.list_recent(limit=1)
    assert recent[0].call_id == "d"
    assert recent[0].note == ""


def test_archive_empty_log_writes_nothing(tmp_path: Path) -> None:
    assert archive_calls(CallLog(), str(tmp_path / "a.jsonl")) == 0


def test_archive_writes_jsonl(tmp_path: Path) -> None:
    log = CallLog()
    log.append(
        CallRecord(
            call_id="c1",
            tenant="t1",
            frames_received=2,
            frames_dropped=0,
            errors=0,
            transcript_chars=5,
            escalated=True,
        )
    )
    path = tmp_path / "sub" / "calls.jsonl"
    assert archive_calls(log, str(path)) == 1
    import json

    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert (row["call_id"], row["escalated"]) == ("c1", True)


def test_create_scheduler_registers_archive_job() -> None:
    scheduler = create_scheduler(CallLog(), "/tmp/x.jsonl", archive_hours=1)
    jobs = scheduler.get_jobs()
    assert [j.id for j in jobs] == ["archive-calls"]
