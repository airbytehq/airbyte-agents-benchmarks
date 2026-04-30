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

import yaml

from agent_bench.metrics import count_tokens

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


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
        records = data["records"]

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
            records=records,
            api_calls=data.get("api_calls", 1),
        ))
    return stats


def _count_records(response: dict) -> int:
    """Best-effort record count from a recording response payload.

    Handles both agent-mcp format (`results[0].result.result`) and native-mcp
    formats (Gong `calls`, Zendesk `tickets`, Salesforce `records`/`searchRecords`,
    Slack `channels`, Linear `issues.nodes`).
    """
    if not isinstance(response, dict):
        return 0

    # Agent-mcp envelope: results[0].result.result
    results_list = response.get("results", [])
    if isinstance(results_list, list) and results_list:
        inner = results_list[0]
        if isinstance(inner, dict) and "result" in inner:
            result_obj = inner.get("result", {})
            if isinstance(result_obj, dict):
                result_data = result_obj.get("result", {})
                if isinstance(result_data, list):
                    return len(result_data)
                if isinstance(result_data, dict):
                    # Nested data key (e.g. gong context store: {data: [...], meta: ...})
                    if "data" in result_data and isinstance(result_data["data"], list):
                        return len(result_data["data"])
                    # Single-record get response
                    if "Id" in result_data or "id" in result_data:
                        return 1
            # Recognized agent-mcp envelope but unrecognized inner shape
            return 0

    # Native-mcp: list responses with known collection keys
    _LIST_KEYS = ("calls", "tickets", "records", "searchRecords", "channels",
                  "messages", "results")
    for key in _LIST_KEYS:
        if key in response and isinstance(response[key], list):
            return len(response[key])

    # Native-mcp: Salesforce SOSL searchRecords (already covered above)
    # Native-mcp: Linear issues.nodes
    if "issues" in response:
        issues = response["issues"]
        if isinstance(issues, dict) and "nodes" in issues:
            return len(issues["nodes"])
        if isinstance(issues, list):
            return len(issues)

    # Native-mcp: single-record get (e.g. Gong `call`, Zendesk `ticket`)
    _SINGULAR_KEYS = ("call", "ticket", "issue")
    for key in _SINGULAR_KEYS:
        if key in response and isinstance(response[key], dict):
            return 1

    # Fallback: response itself looks like a single record
    if "Id" in response or "id" in response:
        return 1

    return 0


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
            total_records += _count_records(response)

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


def load_scenario_metadata() -> dict[str, dict]:
    """Load scenario descriptions, titles, and path tool_calls from YAML files.

    Returns a dict keyed by scenario name (e.g. `linear-search`) with
    `title`, `description`, `annotations`, `is_comparable`, and `paths` sub-keys.
    The `paths` value is a dict mapping path name to its list of tool_call dicts.
    """
    metadata: dict[str, dict] = {}
    if not SCENARIOS_DIR.is_dir():
        return metadata
    for yaml_path in sorted(SCENARIOS_DIR.glob("*.yaml")):
        data = yaml.safe_load(yaml_path.read_text())
        name = data.get("name", yaml_path.stem)
        annotations = data.get("annotations", {})
        paths_raw = data.get("paths", {})
        paths_meta: dict[str, list[dict]] = {}
        for path_name, path_spec in paths_raw.items():
            if isinstance(path_spec, dict):
                paths_meta[path_name] = path_spec.get("tool_calls", [])
        metadata[name] = {
            "title": data.get("title", name),
            "description": data.get("description", "").strip(),
            "annotations": {k: str(v) for k, v in annotations.items()} if annotations else {},
            "is_comparable": data.get("is_comparable", True),
            "paths": paths_meta,
        }
    return metadata


@dataclass
class PerCallStats:
    """Token breakdown for one tool call within a recording."""

    index: int
    tool: str
    server: str
    tokens: int
    records: int


def load_per_call_breakdown(
    artifacts_dir: Path,
    scenario: str,
    path_name: str,
    tool_calls_yaml: list[dict],
) -> list[PerCallStats]:
    """Load per-tool-call token breakdown from a multi-step recording.

    Reads the recording.json for the given scenario+path and computes
    token counts per call. Uses tool_calls from the YAML to label each call.
    """
    recording_file = artifacts_dir / f"{scenario}-scenario" / path_name / "recording.json"
    if not recording_file.exists():
        return []
    data = json.loads(recording_file.read_text())
    if not isinstance(data, list):
        return []

    result: list[PerCallStats] = []
    for i, call in enumerate(data):
        yaml_call = tool_calls_yaml[i] if i < len(tool_calls_yaml) else {}
        server = yaml_call.get("server", call.get("tool", "unknown").split("__")[1] if "__" in call.get("tool", "") else "unknown")
        tool = yaml_call.get("tool", call.get("tool", "unknown"))
        response = call.get("response", {})
        tokens = count_tokens(response)
        records = _count_records(response)
        result.append(PerCallStats(
            index=i,
            tool=tool,
            server=server,
            tokens=tokens,
            records=records,
        ))
    return result


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
            row.note = f"Anomaly: {right_path} returned significantly fewer results"
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
    scenario_meta: dict[str, dict] | None = None,
    artifacts_dir: Path | None = None,
    left_path: str = "agent-mcp",
    right_path: str = "native-mcp",
) -> str:
    """Render a full markdown comparison report."""
    lines: list[str] = []
    run_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    meta = scenario_meta or {}

    lines.append("# Token Efficiency Comparison Report")
    lines.append("")
    lines.append(f"**Date:** {run_date}  ")
    lines.append(f"**Compared paths:** {left_label} vs {right_label}  ")
    connectors = [s.connector for s in summaries]
    lines.append(f"**Connectors:** {', '.join(c.title() for c in connectors)}")
    lines.append("")

    # Per-scenario detail
    lines.append("## Per-Scenario Breakdown")
    lines.append("")
    for s in summaries:
        benchmark_rows = [
            r for r in s.rows
            if meta.get(r.scenario, {}).get("is_comparable", True)
        ]
        not_comparable_rows = [
            r for r in s.rows
            if not meta.get(r.scenario, {}).get("is_comparable", True)
        ]

        if not benchmark_rows and not not_comparable_rows:
            continue

        lines.append(f"### {s.connector.title()}")
        lines.append("")

        if benchmark_rows:
            # Table 1: Scenario Descriptions
            lines.append("#### Scenario Descriptions")
            lines.append("")
            lines.append("| Action | Description | Annotations |")
            lines.append("|---|---|---|")
            for row in benchmark_rows:
                desc = meta.get(row.scenario, {}).get("description", "").strip()
                desc = desc.replace("\n", "<br>")
                scenario_ann = meta.get(row.scenario, {}).get("annotations", {})
                ann_str = "; ".join(v.strip() for v in scenario_ann.values()) if scenario_ann else ""
                lines.append(f"| {row.action} | {desc} | {ann_str} |")
            lines.append("")

            # Table 2: Scenario Benchmark Results
            lines.append("#### Scenario Benchmark Results")
            lines.append("")
            lines.append(
                f"| Action | {left_label} tokens | {right_label} tokens | "
                f"{left_label} records | {right_label} records | Ratio | Savings | Notes |"
            )
            lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
            for row in benchmark_rows:
                left_str = f"{row.left_tokens:,}" if row.left_tokens is not None else "—"
                right_str = f"{row.right_tokens:,}" if row.right_tokens is not None else "—"
                ratio_str = f"{row.ratio_pct:.0f}%" if row.ratio_pct is not None else "N/A"
                savings_str = f"{row.savings_pct:.0f}%" if row.savings_pct is not None else "N/A"
                left_rec = str(row.left_records) if row.left_records is not None else "—"
                right_rec = str(row.right_records) if row.right_records is not None else "—"
                notes_parts: list[str] = []
                scenario_annotations = meta.get(row.scenario, {}).get("annotations", {})
                if scenario_annotations:
                    notes_parts.extend(v.strip() for v in scenario_annotations.values())
                if row.note:
                    notes_parts.append(row.note)
                note_str = "; ".join(notes_parts)
                lines.append(
                    f"| {row.action} | {left_str} | {right_str} | "
                    f"{left_rec} | {right_rec} | {ratio_str} | {savings_str} | {note_str} |"
                )
            bench_left = sum(r.left_tokens for r in benchmark_rows if r.left_tokens)
            bench_right = sum(r.right_tokens for r in benchmark_rows if r.right_tokens)
            if bench_right:
                bench_ratio = bench_left / bench_right * 100
                bench_savings = 100 - bench_ratio
                lines.append("")
                lines.append(
                    f"**Connector total:** {left_label} uses "
                    f"{bench_ratio:.0f}% of {right_label} tokens "
                    f"({bench_savings:.0f}% savings)"
                )
            lines.append("")

            # Per-tool-call breakdown for multi-step scenarios
            if artifacts_dir:
                for row in benchmark_rows:
                    scenario_paths = meta.get(row.scenario, {}).get("paths", {})
                    left_calls_yaml = scenario_paths.get(left_path, [])
                    right_calls_yaml = scenario_paths.get(right_path, [])
                    max_calls = max(len(left_calls_yaml), len(right_calls_yaml))
                    if max_calls <= 1:
                        continue

                    left_breakdown = load_per_call_breakdown(
                        artifacts_dir, row.scenario, left_path, left_calls_yaml,
                    )
                    right_breakdown = load_per_call_breakdown(
                        artifacts_dir, row.scenario, right_path, right_calls_yaml,
                    )
                    if not left_breakdown and not right_breakdown:
                        continue

                    title = meta.get(row.scenario, {}).get("title", row.scenario)
                    lines.append(f"<details><summary>Per-tool-call breakdown: {title}</summary>")
                    lines.append("")

                    if left_breakdown:
                        lines.append(f"**{left_label}** ({len(left_breakdown)} calls)")
                        lines.append("")
                        lines.append("| Step | Server | Tool | Tokens | Records |")
                        lines.append("|---:|---|---|---:|---:|")
                        for pc in left_breakdown:
                            lines.append(
                                f"| {pc.index + 1} | {pc.server} | {pc.tool} "
                                f"| {pc.tokens:,} | {pc.records} |"
                            )
                        lines.append("")

                    if right_breakdown:
                        lines.append(f"**{right_label}** ({len(right_breakdown)} calls)")
                        lines.append("")
                        lines.append("| Step | Server | Tool | Tokens | Records |")
                        lines.append("|---:|---|---|---:|---:|")
                        for pc in right_breakdown:
                            lines.append(
                                f"| {pc.index + 1} | {pc.server} | {pc.tool} "
                                f"| {pc.tokens:,} | {pc.records} |"
                            )
                        lines.append("")

                    lines.append("</details>")
                    lines.append("")

        if not_comparable_rows:
            lines.append("#### Benchmarks Not Comparable")
            lines.append("")
            lines.append(
                "These scenarios could not produce a valid comparison "
                "between Agent MCP and the vendor's native MCP server."
            )
            lines.append("")
            lines.append("| Action | Description | Annotations |")
            lines.append("|---|---|---|")
            for row in not_comparable_rows:
                desc = meta.get(row.scenario, {}).get("description", "").strip()
                desc = desc.replace("\n", "<br>")
                scenario_ann = meta.get(row.scenario, {}).get("annotations", {})
                ann_str = "; ".join(v.strip() for v in scenario_ann.values()) if scenario_ann else ""
                lines.append(f"| {row.action} | {desc} | {ann_str} |")
            lines.append("")

        # Cross-link to scenario YAML definitions (after all sections for this connector)
        all_rows_for_connector = benchmark_rows + not_comparable_rows
        yaml_links = []
        for row in all_rows_for_connector:
            yaml_rel = f"../../src/agent_bench/scenarios/{row.scenario}.yaml"
            yaml_links.append(f"[{row.scenario}]({yaml_rel})")
        if yaml_links:
            lines.append(f"**Scenario definitions:** {' | '.join(yaml_links)}")
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

    # Per-connector summary table at the bottom (benchmark rows only)
    lines.append("## Per-Connector Summary")
    lines.append("")
    lines.append(
        "> :warning: Please review detailed results above for necessary "
        "disclaimers, descriptions of issues, and other explanations."
    )
    lines.append("")
    lines.append(
        f"| Connector | {left_label} tokens | {right_label} tokens | "
        f"Ratio | Savings |"
    )
    lines.append("|---|---:|---:|---:|---:|")
    for s in summaries:
        bench_rows = [
            r for r in s.rows
            if meta.get(r.scenario, {}).get("is_comparable", True)
        ]
        if not bench_rows:
            continue
        left_total = sum(r.left_tokens for r in bench_rows if r.left_tokens)
        right_total = sum(r.right_tokens for r in bench_rows if r.right_tokens)
        ratio_pct = (left_total / right_total * 100) if right_total else None
        savings_pct = (100 - ratio_pct) if ratio_pct is not None else None
        ratio_str = f"{ratio_pct:.0f}%" if ratio_pct is not None else "N/A"
        savings_str = f"{savings_pct:.0f}%" if savings_pct is not None else "N/A"
        lines.append(
            f"| {s.connector.title()} | {left_total:,} | {right_total:,} | "
            f"{ratio_str} | {savings_str} |"
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

    scenario_meta = load_scenario_metadata()
    summaries = build_comparison(stats, left_path, right_path)
    report = render_comparison_markdown(
        summaries, left_label, right_label, date, scenario_meta,
        artifacts_dir=artifacts_dir, left_path=left_path, right_path=right_path,
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)

    return report
