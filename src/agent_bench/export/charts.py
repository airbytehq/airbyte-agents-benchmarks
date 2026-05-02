"""Matplotlib charts for the launch scorecard."""

from __future__ import annotations

from pathlib import Path

from agent_bench.runner import RunReport


PATH_ORDER = ["agent-mcp", "native-mcp"]
PATH_LABEL = {"agent-mcp": "Agent MCP", "native-mcp": "Native MCP"}
PATH_COLOR = {"agent-mcp": "#10b981", "native-mcp": "#f59e0b"}


def render_charts(report: RunReport, out_dir: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise RuntimeError(
            "matplotlib required; install with `uv sync --extra charts`"
        ) from e

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _chart_bar_across_tasks(report, out_dir, plt, "tokens", "Tokens per task", "tokens-bars")
    _chart_bar_across_tasks(report, out_dir, plt, "records", "Records per task", "records-bars")
    _chart_bar_across_tasks(report, out_dir, plt, "calls", "API calls per task", "api-calls")
    _chart_single_record_gap(report, out_dir, plt)


def _cells_by_task(report: RunReport):
    """Yield (connector, label, {path_short: Cell}) for each unique task."""
    groups: dict[tuple[str, str], dict] = {}
    for c in report.cells:
        label = c.scenario.task.label if c.scenario.task else (c.scenario.title or c.scenario.name)
        key = (c.scenario.connector, label)
        groups.setdefault(key, {})[c.path_short] = c
    for (conn, label), by_path in groups.items():
        yield conn, label, by_path


def _chart_bar_across_tasks(report, out_dir, plt, metric: str, title: str, filename: str) -> None:
    tasks = list(_cells_by_task(report))
    n = len(tasks)
    if n == 0:
        return

    fig, ax = plt.subplots(figsize=(max(8, n * 1.1), 5))
    bar_width = 0.27

    for i, slug in enumerate(PATH_ORDER):
        values = []
        for conn, label, by_path in tasks:
            cell = by_path.get(slug)
            v = 0
            if cell and cell.result.status == "ok":
                r = cell.result
                if metric == "tokens":
                    v = r.total_tokens
                elif metric == "records":
                    v = r.total_records
                elif metric == "calls":
                    v = r.api_calls
                elif metric == "latency":
                    v = r.total_latency_ms
            values.append(v)
        xs = [x + i * bar_width for x in range(n)]
        ax.bar(xs, values, bar_width, label=PATH_LABEL[slug], color=PATH_COLOR[slug])

    center_offset = (len(PATH_ORDER) - 1) * bar_width / 2
    ax.set_xticks([x + center_offset for x in range(n)])
    ax.set_xticklabels([f"{conn}\n{label[:22]}" for conn, label, _ in tasks], fontsize=8)
    ax.set_title(title)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / f"{filename}.png", dpi=150)
    fig.savefig(out_dir / f"{filename}.svg")
    plt.close(fig)


def _chart_single_record_gap(report, out_dir, plt) -> None:
    """Hero chart: single-record fetch tokens by path × connector."""
    get_cells = [
        c for c in report.cells
        if c.scenario.inferred_action == "get" and c.result.status == "ok"
    ]
    connectors = sorted({c.scenario.connector for c in get_cells})
    if not connectors:
        return

    fig, ax = plt.subplots(figsize=(max(6, len(connectors) * 2), 5))
    bar_width = 0.27

    for i, slug in enumerate(PATH_ORDER):
        values = []
        for conn in connectors:
            matches = [c for c in get_cells if c.scenario.connector == conn and c.path_short == slug]
            v = matches[0].result.total_tokens if matches else 0
            values.append(v)
        xs = [x + i * bar_width for x in range(len(connectors))]
        ax.bar(xs, values, bar_width, label=PATH_LABEL[slug], color=PATH_COLOR[slug])

    center_offset = (len(PATH_ORDER) - 1) * bar_width / 2
    ax.set_xticks([x + center_offset for x in range(len(connectors))])
    ax.set_xticklabels([c.title() for c in connectors])
    ax.set_title("Single-record fetch cost (tokens)")
    ax.set_ylabel("Tokens")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "single-record-gap.png", dpi=150)
    fig.savefig(out_dir / "single-record-gap.svg")
    plt.close(fig)
