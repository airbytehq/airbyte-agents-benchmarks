"""Benchmark result dataclass with token counting and cost estimation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


# GPT-4o input pricing: $2.50 per 1M tokens
COST_PER_TOKEN = 2.50 / 1_000_000


@dataclass
class StepResult:
    """Result of a single API step."""

    label: str
    latency_ms: float | None
    payload_bytes: int
    tokens: int
    records: int = 0


@dataclass
class BenchmarkResult:
    """Aggregated result for one benchmark path × task."""

    path_name: str
    steps: list[StepResult] = field(default_factory=list)
    relevance_scores: list[float] = field(default_factory=list)
    total_records: int = 0
    # Populated only when the task's action is `get` (single-record fetch).
    # Captures the true cost to retrieve one record, including any
    # search/filter calls a path needs to reach it.
    single_record_calls: int = 0
    single_record_tokens: int = 0
    status: str = "ok"  # "ok" | "skipped" | "error"
    error: str | None = None

    @property
    def total_latency_ms(self) -> float | None:
        """Sum of step latencies, or `None` if no step has a measured value."""
        measured = [s.latency_ms for s in self.steps if s.latency_ms is not None]
        if not measured:
            return None
        return sum(measured)

    @property
    def total_payload_bytes(self) -> int:
        return sum(s.payload_bytes for s in self.steps)

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens for s in self.steps)

    @property
    def api_calls(self) -> int:
        return len(self.steps)

    @property
    def estimated_cost(self) -> float:
        return self.total_tokens * COST_PER_TOKEN

    @property
    def avg_relevance(self) -> float | None:
        if not self.relevance_scores:
            return None
        return sum(self.relevance_scores) / len(self.relevance_scores)


def count_tokens(data: object) -> int:
    """Count tokens for a JSON-serializable object.

    Uses tiktoken (cl100k_base) if available, falls back to word-count heuristic.
    """
    text = json.dumps(data, default=str) if not isinstance(data, str) else data
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # Rough heuristic: ~1.3 tokens per word, ~4 chars per word
        return int(len(text) / 4 * 1.3)


def format_tokens(n: int) -> str:
    """Format token count with ~ prefix and comma separator."""
    return f"~{n:,}"


def format_cost(cost: float) -> str:
    """Format cost as dollar amount."""
    if 0 < cost < 0.001:
        return "<$0.001"
    return f"${cost:.3f}"


def format_bytes(n: int) -> str:
    """Format byte count with comma separator."""
    return f"{n:,} bytes"


def format_latency(ms: float | None) -> str:
    """Format latency in ms with comma separator, or `—` if unmeasured."""
    if ms is None:
        return "—"
    return f"{ms:,.0f}ms"
