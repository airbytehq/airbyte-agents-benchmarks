"""Typer CLI for the three-path Airbyte Agents benchmark."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path as FSPath

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="agent-bench",
    help="Three-way benchmark: Agent SDK vs Agent MCP vs Native MCP.",
    add_completion=False,
    invoke_without_command=False,
)
console = Console()


_ALL_CONNECTORS = ["slack", "linear", "granola"]
_ALL_PATHS = ["agent-sdk", "agent-mcp", "native-mcp"]

_DEFAULT_RECORDINGS = FSPath(__file__).parent.parent.parent / "assets" / "recordings"


def _resolve_connectors(value: str) -> list[str]:
    if value == "all":
        return list(_ALL_CONNECTORS)
    return [s.strip() for s in value.split(",") if s.strip()]


def _resolve_paths(value: str) -> list[str]:
    if value == "all":
        return list(_ALL_PATHS)
    return [s.strip() for s in value.split(",") if s.strip()]


@app.command(name="list")
def list_scenarios() -> None:
    """List available benchmark scenarios."""
    from agent_bench.scenarios.loader import list_scenarios as _list, load_scenario

    for name in _list():
        sc = load_scenario(name)
        console.print(
            f"[cyan]{name}[/cyan] — {sc.title} "
            f"([dim]{len(sc.tasks)} tasks, connector={sc.connector}[/dim])"
        )


@app.command()
def plan(
    connectors: str = typer.Option("all", "--connectors"),
    paths: str = typer.Option("native-mcp,agent-mcp", "--paths", help="Record-replay paths to plan"),
) -> None:
    """Print the MCP tool-call specs that record-replay paths (native-mcp/agent-mcp) would invoke."""
    from agent_bench.config import LiveConfig
    from agent_bench.paths.agent_mcp import AgentMCPPath
    from agent_bench.paths.native_mcp import NativeMCPPath
    from agent_bench.scenarios.loader import load_scenario

    connector_list = _resolve_connectors(connectors)
    path_list = _resolve_paths(paths)

    try:
        config = LiveConfig.from_env(required_connectors=connector_list)
    except EnvironmentError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    for name in connector_list:
        sc = load_scenario(name)
        console.print(f"\n[bold]== {sc.name.upper()} ==[/bold]")
        if "agent-mcp" in path_list:
            connector_id = config.connector_ids[sc.connector]
            console.print("  [magenta]agent-mcp setup[/magenta]:")
            console.print("      [1] mcp__airbyte-agent__describe_connector")
            console.print(f"          args: {json.dumps({'connector_id': connector_id})}")
        for task in sc.tasks:
            console.print(f"\n  [cyan]{task.action}[/cyan] {task.entity} — {task.label}")
            for slug in path_list:
                if slug == "native-mcp":
                    path = NativeMCPPath(_DEFAULT_RECORDINGS / "native-mcp")
                elif slug == "agent-mcp":
                    path = AgentMCPPath(config, _DEFAULT_RECORDINGS / "agent-mcp")
                else:
                    continue
                tplan = path.plan(task, sc)
                console.print(f"    [magenta]{slug}[/magenta]:")
                for idx, call in enumerate(tplan.calls):
                    console.print(f"      [{idx + 1}] {call.tool}")
                    console.print(f"          args: {json.dumps(call.args)}")
                    if call.note:
                        console.print(f"          [dim]note: {call.note}[/dim]")
                for note in tplan.notes:
                    console.print(f"          [dim]note: {note}[/dim]")


@app.command()
def run(
    connectors: str = typer.Option("all", "--connectors"),
    paths: str = typer.Option("all", "--paths"),
    export_markdown: FSPath | None = typer.Option(None, "--export-markdown"),
    export_charts: FSPath | None = typer.Option(None, "--export-charts"),
    export_stats: FSPath | None = typer.Option(None, "--export-stats", help="Directory for per-cell stats JSON files"),
    recordings_dir: FSPath = typer.Option(_DEFAULT_RECORDINGS, "--recordings-dir"),
) -> None:
    """Run the benchmark across the selected connectors and paths."""
    from agent_bench.config import LiveConfig
    from agent_bench.recordings import blocking_issues, validate_recordings
    from agent_bench.runner import run_all

    connector_list = _resolve_connectors(connectors)
    path_list = _resolve_paths(paths)

    export_requested = bool(export_markdown or export_charts or export_stats)
    if export_requested:
        config = None
        if "agent-mcp" in path_list:
            try:
                config = LiveConfig.from_env(required_connectors=connector_list)
            except EnvironmentError as e:
                console.print(f"[red]{e}[/red]")
                raise typer.Exit(1)
        issues = validate_recordings(connector_list, path_list, recordings_dir, config)
        _render_recording_issues(issues)
        errors = blocking_issues(issues)
        if errors:
            console.print("\n[red]Export blocked: required record-replay files are missing or stale.[/red]")
            raise typer.Exit(1)

    def on_cell(cell):
        r = cell.result
        status_color = {"ok": "green", "skipped": "yellow", "error": "red"}.get(r.status, "white")
        line = (
            f"  [{status_color}]{r.status:7}[/{status_color}] "
            f"{cell.scenario.name}/{cell.task.action} × {cell.path_short:6} "
            f"— {r.total_latency_ms:6.0f}ms, {r.total_records:3d} rec, "
            f"{r.total_tokens:6d} tok, {r.api_calls} call"
        )
        if r.error:
            line += f" — {_short_error(r.error)}"
        console.print(line)

    console.print(f"[bold]Running:[/bold] {connector_list} × {path_list}\n")
    report = asyncio.run(run_all(connector_list, path_list, recordings_dir, on_cell=on_cell))

    _render_matrix(report)

    failed_cells = [c for c in report.cells if c.result.status != "ok"]
    if export_requested and failed_cells:
        console.print("\n[red]Export blocked: benchmark run has failed or skipped cells.[/red]")
        for cell in failed_cells:
            console.print(
                f"  [red]{cell.scenario.name}/{cell.task.action} × {cell.path_short}[/red]: "
                f"{_short_error(cell.result.error or cell.result.status)}"
            )
        raise typer.Exit(1)

    consistency_issues = _agent_sdk_mcp_consistency_issues(report)
    if export_requested and consistency_issues:
        console.print("\n[red]Export blocked: Agent SDK/MCP record counts differ.[/red]")
        for issue in consistency_issues:
            console.print(f"  [red]{issue}[/red]")
        raise typer.Exit(1)

    if export_markdown:
        from agent_bench.export.scorecard import render_scorecard
        render_scorecard(report, export_markdown)
        console.print(f"\n[green]scorecard →[/green] {export_markdown}")
    if export_charts:
        from agent_bench.export.charts import render_charts
        render_charts(report, export_charts)
        console.print(f"[green]charts →[/green] {export_charts}")
    if export_stats:
        from agent_bench.export.stats import write_cell_stats
        for cell in report.cells:
            out = write_cell_stats(FSPath(export_stats), cell)
            console.print(f"[green]stats →[/green] {out}")


@app.command()
def validate(
    connectors: str = typer.Option("all", "--connectors"),
    paths: str = typer.Option("native-mcp,agent-mcp", "--paths", help="Record-replay paths to validate"),
    recordings_dir: FSPath = typer.Option(_DEFAULT_RECORDINGS, "--recordings-dir"),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as failures"),
) -> None:
    """Validate required record-replay recordings before exporting a scorecard."""
    from agent_bench.config import LiveConfig
    from agent_bench.recordings import blocking_issues, validate_recordings

    connector_list = _resolve_connectors(connectors)
    path_list = _resolve_paths(paths)
    config = None
    if "agent-mcp" in path_list:
        try:
            config = LiveConfig.from_env(required_connectors=connector_list)
        except EnvironmentError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

    issues = validate_recordings(connector_list, path_list, recordings_dir, config)
    _render_recording_issues(issues)
    errors = blocking_issues(issues)
    if errors or (strict and issues):
        raise typer.Exit(1)
    console.print("[green]recordings ok[/green]")


def _render_matrix(report) -> None:
    """Compact N×M×K matrix print for quick eyeballing."""
    by_sc: dict[str, list] = {}
    for cell in report.cells:
        by_sc.setdefault(cell.scenario.name, []).append(cell)

    for sc_name, cells in by_sc.items():
        table = Table(title=f"{sc_name}", title_justify="left")
        table.add_column("Task", no_wrap=True)
        table.add_column("Path", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Latency", justify="right")
        table.add_column("Records", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Calls", justify="right")
        if any(c.result.error for c in cells):
            table.add_column("Error")
        for c in cells:
            color = {"ok": "green", "skipped": "yellow", "error": "red"}.get(c.result.status, "white")
            row = [
                c.task.label,
                c.path_short,
                f"[{color}]{c.result.status}[/{color}]",
                f"{c.result.total_latency_ms:.0f}ms",
                f"{c.result.total_records}",
                f"{c.result.total_tokens}",
                f"{c.result.api_calls}",
            ]
            if any(cell.result.error for cell in cells):
                row.append(_short_error(c.result.error or ""))
            table.add_row(*row)
        console.print(table)


def _render_recording_issues(issues) -> None:
    if not issues:
        return
    for issue in issues:
        color = "red" if issue.level == "error" else "yellow"
        console.print(f"[{color}]{issue.format()}[/{color}]")


def _short_error(value: str, limit: int = 180) -> str:
    value = " ".join(str(value).split())
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _agent_sdk_mcp_consistency_issues(report) -> list[str]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    for cell in report.cells:
        if cell.path_short in {"agent-sdk", "agent-mcp"}:
            groups.setdefault((cell.scenario.name, cell.task.action), {})[cell.path_short] = cell

    issues: list[str] = []
    for (scenario, action), by_path in groups.items():
        sdk = by_path.get("agent-sdk")
        mcp = by_path.get("agent-mcp")
        if not sdk or not mcp:
            continue
        if sdk.result.status != "ok" or mcp.result.status != "ok":
            continue
        if sdk.result.total_records != mcp.result.total_records:
            issues.append(
                f"{scenario}/{action}: agent-sdk records={sdk.result.total_records}, "
                f"agent-mcp records={mcp.result.total_records}"
            )
    return issues


if __name__ == "__main__":
    app()
