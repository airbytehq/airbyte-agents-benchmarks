"""Generate a markdown comparison report from recording-stats.json files.

Reads per-cell stats files from an artifacts date directory and produces
a side-by-side comparison of token efficiency across paths (typically
agent-mcp vs native-mcp).

Usage:
    from agent_bench.export.comparison import generate_comparison_report
    report_text = generate_comparison_report(Path("artifacts/2026-04-29"))
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agent_bench.metrics import count_tokens


@dataclass
class CellStats:
    """Parsed stats for a single cell (scenario x path)."""

    scenario: str
    connector: str
    path: str
    action: str
    entity: str
    status: str
    tokens: int
    payload_bytes: int
    latency_ms: float | None
    records: int
    api_calls: int


@dataclass
class ComparisonRow:
    """One row in the comparison: a single scenario compared across two paths."""

    scenario: str
    connector: str
    action: str
    left_tokens: int | None = None
    right_tokens: int | None = None
    left_bytes: int | None = None
    right_bytes: int | None = None
    left_records: int | None = None
    right_records: int | None = None
    left_calls: int | None = None
    right_calls: int | None = None
    note: str | None = None

    @property
    def ratio_pct(self) -> float | None:
        """Left tokens as percentage of right tokens. None if either is missing or right is 0."""
        if self.left_tokens is None or self.right_tokens is None:
            return None
        if self.right_tokens == 0:
            return None
        return self.left_tokens / self.right_tokens * 100

    @property
    def savings_pct(self) -> float | None:
        """Percentage token savings (100 - ratio). None if ratio is None."""
        ratio = self.ratio_pct
        if ratio is None:
            return None
        return 100 - ratio


@dataclass
class ConnectorSummary:
    """Aggregate comparison for one connector across all its scenarios."""

    connector: str
    rows: list[ComparisonRow] = field(default_factory=list)

    @property
    def left_total(self) -> int:
        return sum(r.left_tokens for r in self.rows if r.left_tokens is not None)

    @property
    def right_total(self) -> int:
        return sum(r.right_tokens for r in self.rows if r.right_tokens is not None)

    @property
    def ratio_pct(self) -> float | None:
        if self.right_total == 0:
            return None
        return self.left_total / self.right_total * 100

    @property
    def savings_pct(self) -> float | None:
        ratio = self.ratio_pct
        if ratio is None:
            return None
        return 100 - ratio


def load_stats_from_dir(artifacts_dir: Path) -> list[CellStats]:
    """Scan an artifacts date directory for recording-stats.json files."""
    stats: list[CellStats] = []
    if not artifacts_dir.is_dir():
        return stats
    for stats_file in sorted(artifacts_dir.rglob("recording-stats.json")):
        data = json.loads(stats_file.read_text())
        stats.append(CellStats(
            scenario=data["scenario"],
            connector=data["connector"],
            path=data["path"],
            action=data["action"],
            entity=data["entity"],
            status=data["status"],
            tokens=data["tokens"],
            payload_bytes=data["payload_bytes"],
            latency_ms=data.get("latency_ms"),
            records=data.get("records", 0),
            api_calls=data.get("api_calls", 1),
        ))
    return stats


def load_stats_from_recordings(artifacts_dir: Path) -> list[CellStats]:
    """Derive stats from recording.json files when recording-stats.json are absent.

    Computes token counts using `metrics.count_tokens` on the response payload.
    """
    stats: list[CellStats] = []
    if not artifacts_dir.is_dir():
        return stats

    for recording_file in sorted(artifacts_dir.rglob("recording.json")):
        rel = recording_file.relative_to(artifacts_dir)
        parts = rel.parts
        if len(parts) < 3:
            continue
        scenario_dir = parts[0]
        path_name = parts[1]
        if not scenario_dir.endswith("-scenario"):
            continue
        scenario = scenario_dir.removesuffix("-scenario")
        connector = scenario.rsplit("-", 1)[0] if "-" in scenario else scenario
        action = scenario.rsplit("-", 1)[1] if "-" in scenario else "unknown"

        data = json.loads(recording_file.read_text())
        if not isinstance(data, list):
            continue

        total_tokens = 0
        total_bytes = 0
        total_records = 0
        for call in data:
            response = call.get("response", {})
            payload = json.dumps(response, default=str)
            total_bytes += len(payload.encode())
            total_tokens += count_tokens(response)
            # Try to count records from response
            if isinstance(response, dict):
                result = response.get("results", [])
                if isinstance(result, list):
                    for r in result:
                        result_data = r.get("result", {}) if isinstance(r, dict) else {}
                        if isinstance(result_data, dict):
                            for v in result_data.values():
                                if isinstance(v, list):
                                    total_records += len(v)
                                    break

        stats.append(CellStats(
            scenario=scenario,
            connector=connector,
            path=path_name,
            action=action,
            entity="unknown",
            status="ok",
            tokens=total_tokens,
            payload_bytes=total_bytes,
            latency_ms=None,
            records=total_records,
            api_calls=len(data),
        ))
    return stats


def build_comparison(
    stats: list[CellStats],
    left_path: str = "agent-mcp",
    right_path: str = "native-mcp",
) -> list[ConnectorSummary]:
    """Build per-connector comparison summaries from cell stats."""
    # Group by (connector, scenario)
    by_scenario: dict[str, dict[str, CellStats]] = {}
    for s in stats:
        key = s.scenario
        by_scenario.setdefault(key, {})[s.path] = s

    # Build rows grouped by connector
    connector_rows: dict[str, list[ComparisonRow]] = {}
    for scenario, path_map in sorted(by_scenario.items()):
        left = path_map.get(left_path)
        right = path_map.get(right_path)
        if left is None and right is None:
            continue
        connector = (left or right).connector
        row = ComparisonRow(
            scenario=scenario,
            connector=connector,
            action=(left or right).action,
            left_tokens=left.tokens if left else None,
            right_tokens=right.tokens if right else None,
            left_bytes=left.payload_bytes if left else None,
            right_bytes=right.payload_bytes if right else None,
            left_records=left.records if left else None,
            right_records=right.records if right else None,
            left_calls=left.api_calls if left else None,
            right_calls=right.api_calls if right else None,
        )
        # Flag anomalies
        if row.ratio_pct is not None and row.ratio_pct > 200:
            row.note = "Anomaly: right path returned significantly fewer results"
        connector_rows.setdefault(connector, []).append(row)

    summaries = []
    for connector in sorted(connector_rows):
        summaries.append(ConnectorSummary(
            connector=connector,
            rows=connector_rows[connector],
        ))
    return summaries


def render_comparison_markdown(
    summaries: list[ConnectorSummary],
    left_label: str = "Agent MCP",
    right_label: str = "Native MCP",
    date: str | None = None,
) -> str:
    """Render a full markdown comparison report."""
    lines: list[str] = []
    run_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines.append("# Token Efficiency Comparison Report")
    lines.append("")
    lines.append(f"**Date:** {run_date}  ")
    lines.append(f"**Compared paths:** {left_label} vs {right_label}  ")
    connectors = [s.connector for s in summaries]
    lines.append(f"**Connectors:** {', '.join(c.title() for c in connectors)}")
    lines.append("")

    # Grand totals
    grand_left = sum(s.left_total for s in summaries)
    grand_right = sum(s.right_total for s in summaries)
    if grand_right > 0:
        grand_ratio = grand_left / grand_right * 100
        grand_savings = 100 - grand_ratio
        lines.append("## Summary")
        lines.append("")
        lines.append(
            f"**Overall: {left_label} uses {grand_ratio:.0f}% of "
            f"{right_label} tokens ({grand_savings:.0f}% reduction)**"
        )
        lines.append("")
        lines.append(
            f"- {left_label} total: **{grand_left:,}** tokens  "
        )
        lines.append(
            f"- {right_label} total: **{grand_right:,}** tokens  "
        )
        lines.append(
            f"- Token savings: **{grand_savings:.0f}%**"
        )
        lines.append("")

    # Per-connector summary table
    lines.append("## Per-Connector Results")
    lines.append("")
    lines.append(
        f"| Connector | {left_label} tokens | {right_label} tokens | "
        f"Ratio | Savings |"
    )
    lines.append("|---|---:|---:|---:|---:|")
    for s in summaries:
        ratio_str = f"{s.ratio_pct:.0f}%" if s.ratio_pct is not None else "N/A"
        savings_str = f"{s.savings_pct:.0f}%" if s.savings_pct is not None else "N/A"
        lines.append(
            f"| {s.connector.title()} | {s.left_total:,} | {s.right_total:,} | "
            f"{ratio_str} | {savings_str} |"
        )
    lines.append("")

    # Per-scenario detail
    lines.append("## Per-Scenario Breakdown")
    lines.append("")
    for s in summaries:
        lines.append(f"### {s.connector.title()}")
        lines.append("")
        lines.append(
            f"| Action | {left_label} | {right_label} | Ratio | Savings | Notes |"
        )
        lines.append("|---|---:|---:|---:|---:|---|")
        for row in s.rows:
            left_str = f"{row.left_tokens:,}" if row.left_tokens is not None else "—"
            right_str = f"{row.right_tokens:,}" if row.right_tokens is not None else "—"
            ratio_str = f"{row.ratio_pct:.0f}%" if row.ratio_pct is not None else "N/A"
            savings_str = f"{row.savings_pct:.0f}%" if row.savings_pct is not None else "N/A"
            note_str = row.note or ""
            lines.append(
                f"| {row.action} | {left_str} | {right_str} | "
                f"{ratio_str} | {savings_str} | {note_str} |"
            )
        if s.ratio_pct is not None:
            lines.append("")
            lines.append(
                f"**Connector total:** {left_label} uses "
                f"{s.ratio_pct:.0f}% of {right_label} tokens "
                f"({s.savings_pct:.0f}% savings)"
            )
        lines.append("")

    # Methodology note
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        f"- **{left_label}** uses `select_fields` to return only requested fields "
        "(typically 4-9 fields per record)"
    )
    lines.append(
        f"- **{right_label}** returns the vendor API's full response objects "
        "(typically 30-200+ fields per record)"
    )
    lines.append(
        "- Token counts computed with tiktoken `cl100k_base` encoding on raw JSON response payloads"
    )
    lines.append(
        "- Each scenario executes the same logical operation (search/get/list) on both paths"
    )
    lines.append("")

    return "\n".join(lines)


def generate_comparison_report(
    artifacts_dir: Path,
    left_path: str = "agent-mcp",
    right_path: str = "native-mcp",
    left_label: str = "Agent MCP",
    right_label: str = "Native MCP",
    output_path: Path | None = None,
) -> str:
    """High-level entry point: load stats, build comparison, render markdown.

    Tries recording-stats.json first; falls back to deriving stats from recording.json.
    If `output_path` is provided, writes the report there.
    Returns the markdown string.
    """
    stats = load_stats_from_dir(artifacts_dir)
    if not stats:
        stats = load_stats_from_recordings(artifacts_dir)
    if not stats:
        return f"# No data found\n\nNo recording-stats.json or recording.json files in `{artifacts_dir}`.\n"

    # Infer date from directory name
    date = artifacts_dir.name if artifacts_dir.name[0].isdigit() else None

    summaries = build_comparison(stats, left_path, right_path)
    report = render_comparison_markdown(summaries, left_label, right_label, date)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)

    return report
