"""Unit tests for metrics and structured logging."""

import json
import logging

from vaani.logging import JsonFormatter, bind, setup_logging
from vaani.metrics import VaaniMetrics


def test_metrics_counters_and_gauges() -> None:
    m = VaaniMetrics()
    m.record_call_start()
    m.record_call_start()
    m.record_frame()
    m.record_drop()
    m.record_error("transcribe")
    m.record_error("transcribe")
    m.record_call_end()
    assert m.calls_started._value.get() == 2.0
    assert m.frames_received._value.get() == 1.0
    assert m.frames_dropped._value.get() == 1.0
    assert m.call_errors.labels(stage="transcribe")._value.get() == 2.0
    assert m.calls_in_progress._value.get() == 1.0


def test_metrics_observe_and_eval() -> None:
    m = VaaniMetrics()
    m.observe_transcribe(0.5)
    m.observe_agent(1.5)
    m.set_eval_score("tone", "concise", 0.8)
    assert m.transcribe_seconds._sum.get() == 0.5
    assert m.agent_seconds._sum.get() == 1.5
    assert m.eval_score.labels(experiment="tone", variant="concise")._value.get() == 0.8


def test_json_formatter_includes_trace_id() -> None:
    record = logging.LogRecord("t", logging.INFO, "p", 1, "hello", None, None)
    record.trace_id = "abc"
    body = json.loads(JsonFormatter().format(record))
    assert (body["message"], body["trace_id"], body["level"]) == ("hello", "abc", "INFO")


def test_json_formatter_without_trace_id() -> None:
    record = logging.LogRecord("t", logging.ERROR, "p", 1, "boom", None, None)
    body = json.loads(JsonFormatter().format(record))
    assert body["trace_id"] is None
    assert body["level"] == "ERROR"


def test_bind_builds_extra() -> None:
    assert bind("abc", tenant="t1") == {"trace_id": "abc", "tenant": "t1"}


def test_setup_logging_is_idempotent() -> None:
    setup_logging("WARNING")
    count = sum(isinstance(h.formatter, JsonFormatter) for h in logging.getLogger().handlers)
    setup_logging("INFO")
    recount = sum(isinstance(h.formatter, JsonFormatter) for h in logging.getLogger().handlers)
    assert (count, recount) == (1, 1)
    assert logging.getLogger().handlers
