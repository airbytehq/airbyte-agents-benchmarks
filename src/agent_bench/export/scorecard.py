"""Render a marketing-ready scorecard markdown from benchmark results."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from agent_bench.runner import Cell, RunReport


PATH_LABEL = {
    "agent-sdk": "REST Baseline (via SDK)",
    "agent-mcp": "Agent MCP",
    "native-mcp": "Native MCP",
}

PATH_ORDER = ["agent-sdk", "agent-mcp", "native-mcp"]


def render_scorecard(report: RunReport, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    connectors = sorted({c.scenario.connector for c in report.cells})
    final_connectors = {"slack", "linear", "granola"}
    missing_final = sorted(final_connectors - set(connectors))
    included_cells = len(report.cells)
    expected_final_cells = 27
    is_interim = bool(missing_final) or included_cells != expected_final_cells

    lines.append("# Airbyte Agents Launch Benchmark - April 22, 2026")
    lines.append("")
    lines.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}  ")
    lines.append("**Paths compared:** REST Baseline (via SDK) vs Agent MCP vs Native MCP  ")
    lines.append(f"**Connectors:** {', '.join(connectors)}  ")
    lines.append(f"**Cells included:** {included_cells}/{expected_final_cells}")
    if is_interim:
        pending = ", ".join(missing_final) if missing_final else "some benchmark cells"
        lines.append("")
        lines.append(
            f"**Status:** Interim scorecard. {pending.title()} is pending a fresh successful run "
            "before this becomes the final 27-cell launch scorecard."
        )
    lines.append("")
    lines.append(_exec_summary(report, is_interim=is_interim))
    lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append("Three paths race the same three tasks on each connector:")
    lines.append("")
    lines.append("| Path | Transport | Timing |")
    lines.append("|---|---|---|")
    lines.append("| **REST Baseline (via SDK)** | `airbyte-agent-sdk` → Airbyte connector → provider REST API | Client wall-clock |")
    lines.append("| **Agent MCP** | Hosted MCP proxy (`mcp.airbyte.ai`) → Agent REST API | `execution_metadata.execution_time_ms` from the MCP response |")
    lines.append("| **Native MCP** | Vendor-native MCP servers (`mcp__claude_ai_*`) → vendor API | **Not captured.** MCP client tool-call latency is not accessible from the harness; latency reported as 0 and should be read as \"unmeasured in this run\" (see March 3 scorecard for timed reference) |")
    lines.append("")
    lines.append("Metrics:")
    lines.append("- **Records** — count in the response")
    lines.append("- **Tokens** — cl100k (tiktoken) on the raw response payload the agent consumes")
    lines.append("- **Bytes** — UTF-8 length of JSON-encoded response")
    lines.append("- **API calls** - tool invocations per task. In the included Linear list task, native MCP returns 25 records while Airbyte Agents returns 50 records in one call.")
    lines.append("- **Single-record-fetch cost** — tokens + calls to retrieve one record by ID (task 2 only)")
    lines.append("")
    lines.append("Notes:")
    lines.append("- The REST Baseline represents the token cost of consuming the provider's full REST API response. The Airbyte connector fetches records from the third-party provider and passes them through unmodified. `execution_time_ms` from the Agent MCP response reflects server-side processing; client-side wall-clock (REST Baseline path) includes network round-trips and SDK deserialization. See [METHODOLOGY.md](docs/METHODOLOGY.md#agent-sdk-as-rest-baseline) for details.")
    lines.append("- Native MCP connectors return varying shapes: Slack returns markdown-like text, Linear returns structured JSON, Granola returns an aggregated string for list_meetings and a natural-language synthesis for query_granola_meetings.")
    lines.append("")

    for connector in sorted({c.scenario.connector for c in report.cells}):
        cells = [c for c in report.cells if c.scenario.connector == connector]
        lines.append(f"## {connector.title()}")
        lines.append("")
        lines.append(_per_connector_table(cells))
        lines.append("")
        lines.append(_per_connector_takeaway(cells))
        lines.append("")

    lines.append("## Aggregate")
    lines.append("")
    lines.append(_aggregate_table(report))
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    lines.append(_verdict(report))
    lines.append("")

    path.write_text("\n".join(lines))


def _exec_summary(report: RunReport, is_interim: bool = False) -> str:
    # Highlight the headline numbers for the intro paragraph.
    totals = _path_totals(report)
    sdk = totals.get("agent-sdk", _zero_totals())
    mcp = totals.get("agent-mcp", _zero_totals())
    native = totals.get("native-mcp", _zero_totals())

    ratio_mcp_vs_sdk = (sdk["tokens"] / max(mcp["tokens"], 1)) if mcp["tokens"] else None
    ratio_native_vs_mcp = (native["tokens"] / max(mcp["tokens"], 1)) if mcp["tokens"] else None
    prefix = "Interim TL;DR" if is_interim else "TL;DR"

    lines = [
        f"**{prefix}.** Across the three benchmark tasks on each included connector, Airbyte Agents with `select_fields` "
        f"returns roughly **{ratio_mcp_vs_sdk:.1f}× fewer tokens** than the REST Baseline and ships the "
        f"same structured records. It also uses **{ratio_native_vs_mcp:.1f}× fewer tokens** than native vendor MCPs "
        "on the included cells. Compared to native vendor MCPs, Airbyte Agents matches or beats on "
        "record count, single-record-fetch cost, and bulk-list capability - and crucially preserves typed "
        "JSON (vs native MCP's mixed JSON, text, and markdown-like shapes) so agents can filter, "
        "sort, and join programmatically."
        if ratio_mcp_vs_sdk and ratio_native_vs_mcp
        else "**TL;DR.** Airbyte Agents delivers narrower, structured responses vs native vendor MCPs across Linear and Granola."
    ]
    return "\n".join(lines)


def _path_totals(report: RunReport) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for cell in report.cells:
        slot = totals.setdefault(cell.path_short, _zero_totals())
        if cell.result.status != "ok":
            continue
        slot["tokens"] += cell.result.total_tokens
        slot["bytes"] += cell.result.total_payload_bytes
        slot["calls"] += cell.result.api_calls
        slot["latency_ms"] += cell.result.total_latency_ms
        slot["records"] += cell.result.total_records
        slot["n"] += 1
    return totals


def _zero_totals() -> dict[str, float]:
    return {"tokens": 0, "bytes": 0, "calls": 0, "latency_ms": 0, "records": 0, "n": 0}


def _per_connector_table(cells: list[Cell]) -> str:
    """One table: rows are tasks × paths."""
    # Group by task, then emit a row per path
    by_task: dict[str, list[Cell]] = {}
    for c in cells:
        by_task.setdefault(c.task.label, []).append(c)

    lines = [
        "| Task | Path | Records | Tokens | Bytes | Calls | Latency (ms) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for task_label, task_cells in by_task.items():
        by_path = {c.path_short: c for c in task_cells}
        first = True
        for slug in PATH_ORDER:
            c = by_path.get(slug)
            if c is None:
                continue
            r = c.result
            task_cell = task_label if first else ""
            first = False
            status_marker = "" if r.status == "ok" else f" ({r.status})"
            lines.append(
                f"| {task_cell} | {PATH_LABEL[slug]}{status_marker} | "
                f"{r.total_records} | {r.total_tokens:,} | {r.total_payload_bytes:,} | "
                f"{r.api_calls} | {r.total_latency_ms:.0f} |"
            )
    return "\n".join(lines)


def _per_connector_takeaway(cells: list[Cell]) -> str:
    # One-liner summary: cheapest token path and biggest ratio
    ok_cells = [c for c in cells if c.result.status == "ok"]
    if not ok_cells:
        return "*No successful runs for this connector.*"
    by_path_tokens: dict[str, float] = {}
    for c in ok_cells:
        by_path_tokens.setdefault(c.path_short, 0)
        by_path_tokens[c.path_short] += c.result.total_tokens
    if not by_path_tokens:
        return "*No successful runs.*"
    cheapest = min(by_path_tokens, key=by_path_tokens.get)
    cheapest_tokens = by_path_tokens[cheapest]
    highest = max(by_path_tokens, key=by_path_tokens.get)
    highest_tokens = by_path_tokens[highest]
    ratio = highest_tokens / max(cheapest_tokens, 1)
    return (
        f"**Takeaway:** {PATH_LABEL[cheapest]} consumes the fewest tokens "
        f"(**{cheapest_tokens:,.0f}** vs {PATH_LABEL[highest]}'s **{highest_tokens:,.0f}** — "
        f"**{ratio:.1f}× fewer**)."
    )


def _aggregate_table(report: RunReport) -> str:
    totals = _path_totals(report)
    lines = [
        "| Path | Tasks OK | Tokens (sum) | Bytes (sum) | Calls (sum) | Latency ms (sum) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for slug in PATH_ORDER:
        t = totals.get(slug, _zero_totals())
        lines.append(
            f"| {PATH_LABEL[slug]} | {int(t['n'])} | {t['tokens']:,.0f} | "
            f"{t['bytes']:,.0f} | {int(t['calls'])} | {t['latency_ms']:,.0f} |"
        )
    return "\n".join(lines)


def _verdict(report: RunReport) -> str:
    totals = _path_totals(report)
    sdk_tokens = totals.get("agent-sdk", _zero_totals())["tokens"]
    mcp_tokens = totals.get("agent-mcp", _zero_totals())["tokens"]
    native_tokens = totals.get("native-mcp", _zero_totals())["tokens"]
    lines = [
        "- **Agent MCP** (with `select_fields`) is the narrowest path — {:.1f}× fewer tokens than the REST Baseline, {:.1f}× fewer than Native MCP.".format(
            sdk_tokens / max(mcp_tokens, 1) if mcp_tokens else 0,
            native_tokens / max(mcp_tokens, 1) if mcp_tokens else 0,
        ),
        "- **REST Baseline (via SDK)** returns the full typed records from the provider's REST API — the same data an agent would see calling the provider directly. Useful when agents need all fields, e.g. for multi-field joins.",
        "- **Native MCP** is structurally narrower in some cases, but gives up queryability (structured filters) and returns inconsistent shapes across connectors (JSON, text, and markdown-like responses). In the included Linear list task, native MCP returns 25 records while Airbyte Agents returns 50 records in one call.",
        "",
        "**For marketing:** Agent MCP delivers narrower, structured, queryable data in one call. The REST Baseline shows the unfiltered cost. Native MCP requires pagination, returns mixed shapes, and lacks filter operators.",
    ]
    return "\n".join(lines)
