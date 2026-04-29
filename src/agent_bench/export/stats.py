"""Export per-cell stats as immutable JSON artifacts.

Each benchmark cell (one connector x path x task invocation) writes a single
JSON file with normalized metrics. These files are the canonical comparison
unit across runs and invocation mechanisms.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent_bench.runner import Cell

SCHEMA_VERSION = 1


def cell_to_stats(cell: Cell) -> dict:
    """Serialize a single Cell to the normalized stats schema."""
    r = cell.result
    return {
        "schema_version": SCHEMA_VERSION,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "connector": cell.scenario.connector,
        "path": cell.path_short,
        "task": cell.task.action,
        "entity": cell.task.entity,
        "status": r.status,
        "tokens": r.total_tokens,
        "payload_bytes": r.total_payload_bytes,
        "latency_ms": round(r.total_latency_ms, 1) if r.total_latency_ms is not None else None,
        "records": r.total_records,
        "api_calls": r.api_calls,
    }


def stats_path(base_dir: Path, cell: Cell) -> Path:
    """Return the output path for a cell's stats file."""
    return base_dir / cell.path_short / cell.scenario.connector / f"{cell.task.action}-stats.json"


def write_cell_stats(base_dir: Path, cell: Cell) -> Path:
    """Write a single cell's stats JSON and return the file path."""
    out = stats_path(base_dir, cell)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cell_to_stats(cell), indent=2) + "\n")
    return out
