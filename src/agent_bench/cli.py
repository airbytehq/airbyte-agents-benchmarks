"""Typer CLI for the three-path Airbyte Agents benchmark."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path as FSPath

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from agent_bench.airbyte_mcp import (
    DEFAULT_MCP_URL,
    DEFAULT_TOKEN_PATH,
    AirbyteMCPClient,
    FileTokenStorage,
)
from agent_bench.env_manager import DEFAULT_ENV_PATH, populate_env
from agent_bench.recording.agent_mcp_recorder import record_agent_mcp
from agent_bench.recording.common import default_date
from agent_bench.recording.emulated_recorder import record_emulated_agent_mcp
from agent_bench.recording.native_mcp_recorder import record_native_mcp
from agent_bench.recording.single import record_one

app = typer.Typer(
    name="agent-bench",
    help="Two-way benchmark: Agent MCP vs Native MCP.",
    add_completion=False,
    invoke_without_command=False,
)
console = Console()


_ALL_PATHS = ["agent-mcp", "native-mcp"]

PATH_LABEL = {
    "agent-mcp": "Agent MCP",
    "native-mcp": "Native MCP",
}

_DEFAULT_ARTIFACTS = FSPath(__file__).parent.parent.parent / "artifacts"


def _resolve_scenarios(value: str) -> list[str]:
    from agent_bench.scenarios.loader import list_scenarios, scenarios_for_connector
    if value == "all":
        return list_scenarios()
    names: list[str] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        connector_scenarios = scenarios_for_connector(item)
        if connector_scenarios:
            names.extend(connector_scenarios)
        else:
            names.append(item)
    return names


def _resolve_paths(value: str) -> list[str]:
    if value == "all":
        return list(_ALL_PATHS)
    return [s.strip() for s in value.split(",") if s.strip()]


def _resolve_artifacts_dir(artifacts_dir: FSPath, date: str | None) -> FSPath:
    """Resolve the artifacts directory for a given date."""
    if date:
        return artifacts_dir / date
    if not artifacts_dir.is_dir():
        return artifacts_dir / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    candidates = sorted(
        (d for d in artifacts_dir.iterdir() if d.is_dir() and d.name[0].isdigit()),
        reverse=True,
    )
    if candidates:
        return candidates[0]
    return artifacts_dir / datetime.now(timezone.utc).strftime("%Y-%m-%d")


@app.command(name="list")
def list_scenarios_cmd() -> None:
    """List available benchmark scenarios."""
    from agent_bench.scenarios.loader import list_scenarios as _list, load_scenario

    for name in _list():
        sc = load_scenario(name)
        action = sc.task.action if sc.task else "choreographed"
        console.print(
            f"[cyan]{name}[/cyan] — {sc.title} "
            f"([dim]connector={sc.connector}, action={action}[/dim])"
        )


@app.command()
def plan(
    scenarios: str = typer.Option("all", "--scenarios", help="Scenario names or connector names (comma-separated)"),
    paths: str = typer.Option("native-mcp,agent-mcp", "--paths", help="Record-replay paths to plan"),
) -> None:
    """Print the MCP tool-call specs that record-replay paths would invoke."""
    from agent_bench.config import LiveConfig
    from agent_bench.paths.agent_mcp import AgentMCPPath
    from agent_bench.paths.native_mcp import NativeMCPPath
    from agent_bench.scenarios.loader import load_scenario

    scenario_list = _resolve_scenarios(scenarios)
    path_list = _resolve_paths(paths)
    connectors = list({c for n in scenario_list for c in load_scenario(n).connectors})

    try:
        config = LiveConfig.from_env(required_connectors=connectors)
    except EnvironmentError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    for name in scenario_list:
        sc = load_scenario(name)
        console.print(f"\n[bold]== {sc.name} ==[/bold] ({sc.title})")

        if sc.is_choreographed:
            for path_name, path_spec in (sc.paths or {}).items():
                if path_name not in path_list:
                    continue
                console.print(f"  [magenta]{path_name}[/magenta] ({len(path_spec.tool_calls)} call(s)):")
                for idx, tc in enumerate(path_spec.tool_calls):
                    console.print(f"    [{idx + 1}] {tc.server}::{tc.tool}")
                    console.print(f"        args: {json.dumps(tc.args)}")
                    if tc.connector_id_env:
                        console.print(f"        [dim]connector_id_env: {tc.connector_id_env}[/dim]")
        else:
            task = sc.task
            if "agent-mcp" in path_list:
                connector_id = config.connector_ids[sc.connector]
                console.print("  [magenta]agent-mcp setup[/magenta]:")
                console.print("      [1] mcp__airbyte-agent__describe_connector")
                console.print(f"          args: {json.dumps({'connector_id': connector_id})}")
            console.print(f"\n  [cyan]{task.action}[/cyan] {task.entity} — {task.label}")
            for slug in path_list:
                if slug == "native-mcp":
                    path = NativeMCPPath(FSPath("/dev/null"))
                elif slug == "agent-mcp":
                    path = AgentMCPPath(config, FSPath("/dev/null"))
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
    scenarios: str = typer.Option("all", "--scenarios", help="Scenario names or connector names (comma-separated)"),
    paths: str = typer.Option("all", "--paths"),
    artifacts_dir: FSPath = typer.Option(_DEFAULT_ARTIFACTS, "--artifacts-dir"),
    date: str | None = typer.Option(None, "--date", help="Artifact date folder (e.g. 2026-04-24). Defaults to latest."),
    mode: str = typer.Option("live", "--mode", help="Execution mode: 'live' (default) makes real API calls, 'replay' uses recorded responses."),
    export_markdown: FSPath | None = typer.Option(None, "--export-markdown"),
    export_charts: FSPath | None = typer.Option(None, "--export-charts"),
    export_stats: bool = typer.Option(False, "--export-stats", help="Write recording-stats.json alongside recordings"),
) -> None:
    """Run the benchmark across the selected scenarios and paths."""
    from agent_bench.config import LiveConfig
    from agent_bench.recordings import blocking_issues, validate_recordings
    from agent_bench.runner import run_all
    from agent_bench.scenarios.loader import load_scenario

    if mode not in ("live", "replay"):
        console.print(f"[red]Invalid mode {mode!r}. Must be 'live' or 'replay'.[/red]")
        raise typer.Exit(1)

    scenario_list = _resolve_scenarios(scenarios)
    path_list = _resolve_paths(paths)
    dated_dir = _resolve_artifacts_dir(artifacts_dir, date)

    if mode == "live" and "native-mcp" in path_list:
        console.print("[red]native-mcp does not support live mode (requires vendor MCP servers). Use --mode replay or remove native-mcp from --paths.[/red]")
        raise typer.Exit(1)

    export_requested = bool(export_markdown or export_charts or export_stats)
    if export_requested:
        config = None
        connectors = list({c for n in scenario_list for c in load_scenario(n).connectors})
        if "agent-mcp" in path_list:
            try:
                config = LiveConfig.from_env(required_connectors=connectors)
            except EnvironmentError as e:
                console.print(f"[red]{e}[/red]")
                raise typer.Exit(1)
        issues = validate_recordings(scenario_list, path_list, dated_dir, config)
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
            f"{cell.scenario.name} × {cell.path_short:10} "
            f"— {r.total_records:3d} rec, "
            f"{r.total_tokens:6d} tok, {r.api_calls} call"
        )
        if r.error:
            line += f" — {_short_error(r.error)}"
        console.print(line)

    console.print(f"[bold]Running:[/bold] {scenario_list} × {path_list} [dim](mode={mode})[/dim]")
    console.print(f"[dim]Artifacts dir: {dated_dir}[/dim]\n")
    report = asyncio.run(run_all(scenario_list, path_list, dated_dir, on_cell=on_cell, mode=mode))

    _render_matrix(report)

    failed_cells = [c for c in report.cells if c.result.status != "ok"]
    if export_requested and failed_cells:
        console.print("\n[red]Export blocked: benchmark run has failed or skipped cells.[/red]")
        for cell in failed_cells:
            console.print(
                f"  [red]{cell.scenario.name} × {cell.path_short}[/red]: "
                f"{_short_error(cell.result.error or cell.result.status)}"
            )
        raise typer.Exit(1)

    if export_stats:
        from agent_bench.export.stats import write_cell_stats
        for cell in report.cells:
            out = write_cell_stats(dated_dir, cell)
            console.print(f"[green]stats →[/green] {out}")

    if export_markdown:
        from agent_bench.export.scorecard import render_scorecard
        target = export_markdown if str(export_markdown) != "auto" else dated_dir / "benchmark-result-report.md"
        render_scorecard(report, target)
        console.print(f"\n[green]scorecard →[/green] {target}")
        _update_symlink(target, artifacts_dir)
    if export_charts:
        from agent_bench.export.charts import render_charts
        render_charts(report, export_charts)
        console.print(f"[green]charts →[/green] {export_charts}")


@app.command()
def validate(
    scenarios: str = typer.Option("all", "--scenarios", help="Scenario names or connector names (comma-separated)"),
    paths: str = typer.Option("native-mcp,agent-mcp", "--paths", help="Record-replay paths to validate"),
    artifacts_dir: FSPath = typer.Option(_DEFAULT_ARTIFACTS, "--artifacts-dir"),
    date: str | None = typer.Option(None, "--date", help="Artifact date folder. Defaults to latest."),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as failures"),
) -> None:
    """Validate required record-replay recordings before exporting."""
    from agent_bench.config import LiveConfig
    from agent_bench.recordings import blocking_issues, validate_recordings
    from agent_bench.scenarios.loader import load_scenario

    scenario_list = _resolve_scenarios(scenarios)
    path_list = _resolve_paths(paths)
    dated_dir = _resolve_artifacts_dir(artifacts_dir, date)
    connectors = list({c for n in scenario_list for c in load_scenario(n).connectors})

    config = None
    if "agent-mcp" in path_list:
        try:
            config = LiveConfig.from_env(required_connectors=connectors)
        except EnvironmentError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

    issues = validate_recordings(scenario_list, path_list, dated_dir, config)
    _render_recording_issues(issues)
    errors = blocking_issues(issues)
    if errors or (strict and issues):
        raise typer.Exit(1)
    console.print("[green]recordings ok[/green]")


@app.command(name="generate-stats")
def generate_stats_cmd(
    artifacts_dir: FSPath = typer.Option(_DEFAULT_ARTIFACTS, "--artifacts-dir"),
    date: str | None = typer.Option(None, "--date", help="Artifact date folder (e.g. 2026-04-30). Defaults to latest."),
) -> None:
    """Generate recording-stats.json from existing recording.json files.

    Derives aggregate metrics (tokens, records, latency) from raw recordings.
    Useful for (re-)generating stats files that can be committed to the repo
    so other sessions can produce reports without needing raw recordings.
    """
    from agent_bench.export.stats import write_stats_for_dir

    dated_dir = _resolve_artifacts_dir(artifacts_dir, date)
    if not dated_dir.is_dir():
        console.print(f"[red]Artifacts directory not found: {dated_dir}[/red]")
        raise typer.Exit(1)

    count = write_stats_for_dir(dated_dir)
    if not count:
        console.print(f"[yellow]No recording.json files found in {dated_dir}[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]wrote {count} recording-stats.json files in {dated_dir}[/green]")


@app.command()
def compare(
    artifacts_dir: FSPath = typer.Option(_DEFAULT_ARTIFACTS, "--artifacts-dir"),
    date: str | None = typer.Option(None, "--date", help="Artifact date folder (e.g. 2026-04-29). Defaults to latest."),
    left: str = typer.Option("agent-mcp", "--left", help="Left path slug for comparison"),
    right: str = typer.Option("native-mcp", "--right", help="Right path slug for comparison"),
    output: FSPath | None = typer.Option(None, "--output", "-o", help="Write markdown report to this file"),
) -> None:
    """Generate a markdown comparison report from recording-stats.json files.

    Compares token efficiency between two paths (default: agent-mcp vs native-mcp).
    Falls back to deriving stats from recording.json if stats files are absent.
    """
    from agent_bench.export.comparison import generate_comparison_report

    dated_dir = _resolve_artifacts_dir(artifacts_dir, date)
    if not dated_dir.is_dir():
        console.print(f"[red]Artifacts directory not found: {dated_dir}[/red]")
        raise typer.Exit(1)

    left_label = PATH_LABEL.get(left, left)
    right_label = PATH_LABEL.get(right, right)

    report = generate_comparison_report(
        artifacts_dir=dated_dir,
        left_path=left,
        right_path=right,
        left_label=left_label,
        right_label=right_label,
        output_path=output,
    )

    if output:
        console.print(f"[green]report →[/green] {output}")
    else:
        console.print(report)


def _render_matrix(report) -> None:
    """Compact matrix print for quick eyeballing."""
    table = Table(title="Results", title_justify="left")
    table.add_column("Scenario", no_wrap=True)
    table.add_column("Path", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Records", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Calls", justify="right")
    if any(c.result.error for c in report.cells):
        table.add_column("Error")
    for c in report.cells:
        color = {"ok": "green", "skipped": "yellow", "error": "red"}.get(c.result.status, "white")
        row = [
            c.scenario.name,
            c.path_short,
            f"[{color}]{c.result.status}[/{color}]",
            f"{c.result.total_records}",
            f"{c.result.total_tokens}",
            f"{c.result.api_calls}",
        ]
        if any(cell.result.error for cell in report.cells):
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


def _update_symlink(report_path: FSPath, artifacts_root: FSPath) -> None:
    """Update the `latest_comparison_report/README.md` symlink at repo root."""
    repo_root = artifacts_root.parent
    symlink_dir = repo_root / "latest_comparison_report"
    symlink_dir.mkdir(exist_ok=True)
    symlink = symlink_dir / "README.md"
    rel = os.path.relpath(report_path, symlink_dir)
    try:
        if symlink.is_symlink() or symlink.exists():
            symlink.unlink()
        symlink.symlink_to(rel)
        console.print(f"[green]symlink →[/green] {symlink} -> {rel}")
    except OSError as exc:
        console.print(f"[yellow]warning:[/yellow] could not update symlink: {exc}")


@app.command(name="populate-env")
def populate_env_cmd(
    output: FSPath = typer.Option(DEFAULT_ENV_PATH, "--output", "-o", help="Path to write the .env file."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing values instead of preserving them."),
) -> None:
    """Populate `.env` from 1Password credentials.

    Reads `.env.template` for the list of accepted variables, fetches
    native-MCP connector secrets from the `direct-connector-credentials`
    vault, and writes a `.env` file.  Agent-MCP variables not stored in
    1Password are left blank for manual entry.

    Existing values in the output file are preserved unless `--overwrite`
    is passed.
    """
    out = populate_env(output_path=FSPath(output), overwrite=overwrite)
    console.print(f"[green]Wrote {out}[/green]")


@app.command()
def auth(
    server_url: str = typer.Option(DEFAULT_MCP_URL, "--server-url", help="MCP server URL."),
    token_path: FSPath = typer.Option(DEFAULT_TOKEN_PATH, "--token-path", help="Path to persist OAuth tokens."),
) -> None:
    """One-time browser OAuth for `mcp.airbyte.ai`.

    Opens a browser, completes the PKCE flow, and persists the resulting
    access + refresh tokens. Re-run if you see 401 responses during recording.
    """
    load_dotenv()
    env_token_path = os.environ.get("AIRBYTE_TOKEN_PATH")
    if env_token_path and token_path == DEFAULT_TOKEN_PATH:
        token_path = FSPath(env_token_path)

    async def _auth() -> None:
        storage = FileTokenStorage(token_path)
        client = AirbyteMCPClient(server_url=server_url, storage=storage)
        try:
            await client.initialize()
        finally:
            await client.close()
        console.print(f"[green]Authenticated. Tokens saved to {token_path}.[/green]")

    asyncio.run(_auth())


@app.command()
def record(
    path: str = typer.Option(..., "--path", help="Recording path: 'agent-mcp' or 'native-mcp'."),
    connectors: str = typer.Option("all", "--connectors", help="Comma-separated connector names, or 'all'."),
    date: str | None = typer.Option(None, "--date", help="Artifact date folder (YYYY-MM-DD). Defaults to today UTC."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be recorded without executing."),
    emulated_mcp: bool = typer.Option(False, "--emulated-mcp/--no-emulated-mcp", help="Use Sonar REST API instead of real MCP (agent-mcp only)."),
    server_url: str = typer.Option(DEFAULT_MCP_URL, "--server-url", help="MCP server URL (agent-mcp, real MCP only)."),
    token_path: FSPath = typer.Option(DEFAULT_TOKEN_PATH, "--token-path", help="OAuth token path (agent-mcp, real MCP only)."),
) -> None:
    """Record MCP responses for benchmark replay.

    Captures live responses from either the Airbyte Agent MCP server or
    vendor-native MCP servers and writes them as recording artifacts.
    """
    if path not in ("agent-mcp", "native-mcp"):
        console.print(f"[red]Invalid --path {path!r}. Must be 'agent-mcp' or 'native-mcp'.[/red]")
        raise typer.Exit(1)

    connector_arg = None if connectors == "all" else connectors

    if path == "native-mcp":
        if emulated_mcp:
            console.print("[red]Emulated MCP is not available for native-mcp path.[/red]")
            raise typer.Exit(1)
        rc = record_native_mcp(connectors=connector_arg, date=date, dry_run=dry_run)

    elif emulated_mcp:
        rc = record_emulated_agent_mcp(connectors=connector_arg, date=date, dry_run=dry_run)

    else:
        rc = asyncio.run(
            record_agent_mcp(
                connectors=connector_arg,
                date=date,
                server_url=server_url,
                token_path=token_path,
                dry_run=dry_run,
            )
        )

    if rc != 0:
        raise typer.Exit(rc)


@app.command(name="record-one")
def record_one_cmd(
    path: str = typer.Option(..., "--path", help="Recording path: 'native-mcp' or 'agent-mcp'."),
    scenario: str = typer.Option(..., "--scenario", help="Scenario name, e.g. linear-search."),
    tool: str = typer.Option(..., "--tool", help="MCP tool name."),
    args: str = typer.Option(..., "--args", help="JSON string of tool arguments."),
    response_file: FSPath = typer.Option(..., "--response-file", help="Path to a file with the raw response JSON."),
    date: str | None = typer.Option(None, "--date", help="Artifact date folder (YYYY-MM-DD). Defaults to today UTC."),
    wall_ms: float | None = typer.Option(None, "--wall-ms", help="Wall-clock ms. For agent-mcp, defaults to execution_metadata.execution_time_ms."),
    reset: bool = typer.Option(False, "--reset", help="Overwrite any existing recording for this scenario."),
) -> None:
    """Save a single MCP tool-call response as a benchmark recording."""
    if path not in ("native-mcp", "agent-mcp"):
        console.print(f"[red]Invalid --path {path!r}. Must be 'native-mcp' or 'agent-mcp'.[/red]")
        raise typer.Exit(1)

    date_str = date or default_date()
    out_path = record_one(
        path_slug=path,
        scenario=scenario,
        tool=tool,
        args_json=args,
        response_file=response_file,
        date=date_str,
        wall_ms=wall_ms,
        reset=reset,
    )
    existing = json.loads(out_path.read_text())
    console.print(f"saved -> {out_path} ({len(existing)} call(s))")


if __name__ == "__main__":
    app()
