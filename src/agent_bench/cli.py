"""Typer CLI for the three-path Airbyte Agents benchmark."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path as FSPath

import httpx
import typer
from dotenv import load_dotenv
from rich.console import Console

from agent_bench.airbyte_mcp import (
    DEFAULT_MCP_URL,
    DEFAULT_TOKEN_PATH,
    AirbyteMCPClient,
    FileTokenStorage,
)
from agent_bench.env_manager import DEFAULT_ENV_PATH, populate_env
from agent_bench.export.comparison import generate_comparison_report
from agent_bench.export.stats import write_stats_for_dir
from agent_bench.recording.agent_mcp_recorder import record_agent_mcp
from agent_bench.recording.common import ARTIFACTS_ROOT, default_date
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


PATH_LABEL = {
    "agent-mcp": "Agent MCP",
    "native-mcp": "Native MCP",
}

_DEFAULT_ARTIFACTS = FSPath(__file__).parent.parent.parent / "artifacts"


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

    try:
        asyncio.run(_auth())
    except httpx.ConnectError as exc:
        console.print(f"[red]Cannot reach MCP server at {server_url}: {exc}[/red]")
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]MCP server returned HTTP {exc.response.status_code}: {exc}[/red]")
        raise typer.Exit(1) from None
    except TimeoutError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Ensure your browser completed the OAuth flow and the redirect reached localhost.")
        raise typer.Exit(1) from None


@app.command()
def record(
    path: str | None = typer.Option(None, "--path", help="Recording path: 'agent-mcp' or 'native-mcp'. Optional with --stats-only."),
    connectors: str = typer.Option("all", "--connectors", help="Comma-separated connector names, or 'all'."),
    date: str | None = typer.Option(None, "--date", help="Artifact date folder (YYYY-MM-DD). Defaults to today (or latest for --stats-only)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be recorded without executing."),
    stats_only: bool = typer.Option(False, "--stats-only", help="Regenerate stats from existing recordings without re-recording."),
    emulated_mcp: bool = typer.Option(False, "--emulated-mcp/--no-emulated-mcp", help="Use Sonar REST API instead of real MCP (agent-mcp only)."),
    server_url: str = typer.Option(DEFAULT_MCP_URL, "--server-url", help="MCP server URL (agent-mcp, real MCP only)."),
    token_path: FSPath = typer.Option(DEFAULT_TOKEN_PATH, "--token-path", help="OAuth token path (agent-mcp, real MCP only)."),
) -> None:
    """Record MCP responses for benchmark replay.

    Captures live responses from either the Airbyte Agent MCP server or
    vendor-native MCP servers and writes them as recording artifacts.
    Automatically generates `recording-stats.json` after recording.

    Use `--stats-only` to regenerate stats from existing recordings
    without re-recording. In this mode `--path` is not required and
    `--date` defaults to the latest artifacts directory.
    """
    if stats_only:
        dated_dir = _resolve_artifacts_dir(_DEFAULT_ARTIFACTS, date)
        if not dated_dir.is_dir():
            console.print(f"[red]Artifacts directory not found: {dated_dir}[/red]")
            raise typer.Exit(1)
        count = write_stats_for_dir(dated_dir)
        if count:
            console.print(f"[green]Wrote {count} recording-stats.json file(s) in {dated_dir}[/green]")
        else:
            console.print(f"[red]No recording.json files found in {dated_dir}[/red]")
            raise typer.Exit(1)
        return

    if not path or path not in ("agent-mcp", "native-mcp"):
        console.print(f"[red]--path is required and must be 'agent-mcp' or 'native-mcp'.[/red]")
        raise typer.Exit(1)

    resolved_date = date or default_date()
    dated_dir = ARTIFACTS_ROOT / resolved_date
    connector_arg = None if connectors == "all" else connectors

    if path == "native-mcp":
        if emulated_mcp:
            console.print("[red]Emulated MCP is not available for native-mcp path.[/red]")
            raise typer.Exit(1)
        rc = record_native_mcp(connectors=connector_arg, date=resolved_date, dry_run=dry_run)

    elif emulated_mcp:
        rc = record_emulated_agent_mcp(connectors=connector_arg, date=resolved_date, dry_run=dry_run)

    else:
        rc = asyncio.run(
            record_agent_mcp(
                connectors=connector_arg,
                date=resolved_date,
                server_url=server_url,
                token_path=token_path,
                dry_run=dry_run,
            )
        )

    if rc != 0:
        console.print(f"[red]Recording failed (exit code {rc}). See errors above.[/red]")
        raise typer.Exit(rc)

    if dry_run:
        return

    if not dated_dir.is_dir():
        console.print(f"[yellow]No artifacts directory at {dated_dir} — skipping stats generation.[/yellow]")
        return

    count = write_stats_for_dir(dated_dir)
    if count:
        console.print(f"[green]Wrote {count} recording-stats.json file(s) in {dated_dir}[/green]")
    else:
        console.print(f"[yellow]No recording.json files found in {dated_dir}[/yellow]")


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
