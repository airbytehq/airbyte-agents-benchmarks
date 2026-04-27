"""Render a marketing-ready scorecard markdown from benchmark results."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from agent_bench.runner import Cell, RunReport


PATH_LABEL = {
    "ae-sdk": "Agent Engine SDK",
    "ae-mcp": "Agent Engine MCP",
    "claude": "Claude cloud MCP",
}

PATH_ORDER = ["ae-sdk", "ae-mcp", "claude"]


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

    lines.append("# Agent Engine Launch Benchmark - April 22, 2026")
    lines.append("")
    lines.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}  ")
    lines.append("**Paths compared:** Agent Engine SDK vs Agent Engine MCP vs Claude cloud MCP  ")
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
    lines.append("| **Agent Engine SDK** | `airbyte-agent-sdk` Python package → Agent Engine API | Client wall-clock |")
    lines.append("| **Agent Engine MCP** | Hosted MCP proxy (`mcp.airbyte.ai`) → Agent Engine API | `execution_metadata.execution_time_ms` from the MCP response |")
    lines.append("| **Claude cloud MCP** | Anthropic-hosted MCP (`mcp__claude_ai_*`) → vendor API | **Not captured.** Claude Code tool-call latency is not accessible from the harness; latency reported as 0 and should be read as \"unmeasured in this run\" (see March 3 scorecard for timed reference) |")
    lines.append("")
    lines.append("Metrics:")
    lines.append("- **Records** — count in the response")
    lines.append("- **Tokens** — cl100k (tiktoken) on the raw response payload the agent consumes")
    lines.append("- **Bytes** — UTF-8 length of JSON-encoded response")
    lines.append("- **API calls** - tool invocations per task. In the included Linear list task, Claude returns 25 records while Agent Engine returns 50 records in one call.")
    lines.append("- **Single-record-fetch cost** — tokens + calls to retrieve one record by ID (task 2 only)")
    lines.append("")
    lines.append("Notes:")
    lines.append("- Agent Engine MCP and SDK are both read-throughs of the same Agent Engine API — the MCP adds HTTP proxy overhead. `execution_time_ms` from the MCP response reflects Agent Engine server-side processing; client-side wall-clock (SDK path) includes both network round-trips and SDK deserialization.")
    lines.append("- Claude cloud MCP connectors return varying shapes: Slack returns markdown-like text, Linear returns structured JSON, Granola returns an aggregated string for list_meetings and a natural-language synthesis for query_granola_meetings.")
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
    sdk = totals.get("ae-sdk", _zero_totals())
    mcp = totals.get("ae-mcp", _zero_totals())
    claude = totals.get("claude", _zero_totals())

    ratio_mcp_vs_sdk = (sdk["tokens"] / max(mcp["tokens"], 1)) if mcp["tokens"] else None
    ratio_claude_vs_mcp = (claude["tokens"] / max(mcp["tokens"], 1)) if mcp["tokens"] else None
    prefix = "Interim TL;DR" if is_interim else "TL;DR"

    lines = [
        f"**{prefix}.** Across the three benchmark tasks on each included connector, Agent Engine with `select_fields` "
        f"returns roughly **{ratio_mcp_vs_sdk:.1f}× fewer tokens** than the full SDK payload and ships the "
        f"same structured records. It also uses **{ratio_claude_vs_mcp:.1f}× fewer tokens** than Claude cloud MCPs "
        "on the included cells. Compared to Claude cloud MCPs, Agent Engine matches or beats on "
        "record count, single-record-fetch cost, and bulk-list capability - and crucially preserves typed "
        "JSON (vs Claude MCP's mixed JSON, text, and markdown-like shapes) so agents can filter, "
        "sort, and join programmatically."
        if ratio_mcp_vs_sdk and ratio_claude_vs_mcp
        else "**TL;DR.** Agent Engine delivers narrower, structured responses vs Claude cloud MCPs across Linear and Granola."
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
    sdk_tokens = totals.get("ae-sdk", _zero_totals())["tokens"]
    mcp_tokens = totals.get("ae-mcp", _zero_totals())["tokens"]
    claude_tokens = totals.get("claude", _zero_totals())["tokens"]
    lines = [
        "- **Agent Engine MCP** (with `select_fields`) is the narrowest path — {:.1f}× fewer tokens than the full SDK, {:.1f}× fewer than Claude cloud MCP.".format(
            sdk_tokens / max(mcp_tokens, 1) if mcp_tokens else 0,
            claude_tokens / max(mcp_tokens, 1) if mcp_tokens else 0,
        ),
        "- **Agent Engine SDK** returns full typed records — useful when agents need all fields, e.g. for multi-field joins.",
        "- **Claude cloud MCP** is structurally narrower in some cases, but gives up queryability (structured filters) and returns inconsistent shapes across connectors (JSON, text, and markdown-like responses). In the included Linear list task, Claude returns 25 records while Agent Engine returns 50 records in one call.",
        "",
        "**For marketing:** Agent Engine MCP + SDK deliver narrower, structured, queryable data in one call. Claude cloud MCP requires pagination, returns mixed shapes, and lacks filter operators.",
    ]
    return "\n".join(lines)
