"""Export per-cell stats as immutable JSON artifacts.

Each benchmark cell (one scenario x path invocation) writes a single
JSON file with normalized metrics. These files are the canonical comparison
unit across runs and invocation mechanisms.

Output path: `{artifacts_dir}/{scenario}-scenario/{path}/recording-stats.json`
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2


def build_stats_dict(
    *,
    scenario: str,
    connector: str,
    path: str,
    action: str,
    entity: str,
    status: str,
    tokens: int,
    payload_bytes: int,
    latency_ms: float | None,
    records: int,
    api_calls: int,
) -> dict:
    """Build the canonical stats JSON dict from flat field values."""
    return {
        "schema_version": SCHEMA_VERSION,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario,
        "connector": connector,
        "path": path,
        "action": action,
        "entity": entity,
        "status": status,
        "tokens": tokens,
        "payload_bytes": payload_bytes,
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        "records": records,
        "api_calls": api_calls,
    }


def write_stats_for_dir(artifacts_dir: Path) -> int:
    """Generate `recording-stats.json` from sibling `recording.json` files.

    Returns the number of stats files written.
    """
    from agent_bench.export.comparison import load_stats_from_recordings

    stats = load_stats_from_recordings(artifacts_dir)
    count = 0
    for s in stats:
        out_path = artifacts_dir / f"{s.scenario}-scenario" / s.path / "recording-stats.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = build_stats_dict(
            scenario=s.scenario,
            connector=s.connector,
            path=s.path,
            action=s.action,
            entity=s.entity,
            status=s.status,
            tokens=s.tokens,
            payload_bytes=s.payload_bytes,
            latency_ms=s.latency_ms,
            records=s.records,
            api_calls=s.api_calls,
        )
        out_path.write_text(json.dumps(data, indent=2) + "\n")
        count += 1
    return count
