"""Prometheus metrics. One instance per process (main wires the module one)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class VaaniMetrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry()
        self.calls_started = Counter(
            "vaani_calls_started_total",
            "Calls accepted on the WebSocket endpoint.",
            registry=self.registry,
        )
        self.frames_received = Counter(
            "vaani_frames_received_total", "Audio frames received.", registry=self.registry
        )
        self.frames_dropped = Counter(
            "vaani_frames_dropped_total",
            "Audio frames dropped by backpressure coalescing.",
            registry=self.registry,
        )
        self.call_errors = Counter(
            "vaani_call_errors_total",
            "Provider/stage failures during calls.",
            ["stage"],
            registry=self.registry,
        )
        self.calls_in_progress = Gauge(
            "vaani_calls_in_progress", "Calls currently open.", registry=self.registry
        )
        self.transcribe_seconds = Histogram(
            "vaani_transcribe_seconds",
            "Speech-to-text latency.",
            registry=self.registry,
        )
        self.agent_seconds = Histogram(
            "vaani_agent_seconds", "Agent turn latency.", registry=self.registry
        )
        self.eval_score = Gauge(
            "vaani_eval_score",
            "Latest experiment mean score by variant.",
            ["experiment", "variant"],
            registry=self.registry,
        )

    def record_call_start(self) -> None:
        self.calls_started.inc()
        self.calls_in_progress.inc()

    def record_call_end(self) -> None:
        self.calls_in_progress.dec()

    def record_frame(self) -> None:
        self.frames_received.inc()

    def record_drop(self) -> None:
        self.frames_dropped.inc()

    def record_error(self, stage: str) -> None:
        self.call_errors.labels(stage=stage).inc()

    def observe_transcribe(self, seconds: float) -> None:
        self.transcribe_seconds.observe(seconds)

    def observe_agent(self, seconds: float) -> None:
        self.agent_seconds.observe(seconds)

    def set_eval_score(self, experiment: str, variant: str, score: float) -> None:
        self.eval_score.labels(experiment=experiment, variant=variant).set(score)


metrics = VaaniMetrics()
