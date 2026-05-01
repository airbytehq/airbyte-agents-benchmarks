# Reproducing the Benchmark

This guide walks through reproducing the Airbyte Agents launch benchmark results from scratch. It covers three tiers: stats-only (no credentials), recording agent-mcp (Airbyte Cloud credentials), and full benchmark (all connectors).

## Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) package manager
- Git

Clone and install:

```bash
git clone https://github.com/airbytehq/airbyte-agents-benchmarks.git
cd airbyte-agents-benchmarks
uv sync
```

Verify the install:

```bash
uv run agent-bench list
```

## Tier 1: Stats-Only (No Credentials)

The committed `recording-stats.json` files in `artifacts/YYYY-MM-DD/` contain aggregate metrics (token counts, latency, record counts). Raw `recording.json` files are gitignored and never committed. You can run tests and generate comparison reports without any API credentials or recordings.

### Run tests

```bash
uv run pytest -q
```

All tests should pass.

### Generate comparison report

```bash
uv run agent-bench compare
```

This reads the committed `recording-stats.json` files and produces a markdown comparison of token efficiency across connectors. No credentials or raw recordings needed.

### List scenarios

```bash
uv run agent-bench list
```

Shows all available benchmark scenarios and their connector mappings.

## Tier 2: Recording Agent MCP (Requires Credentials)

Recording new Agent MCP responses (and running the live `agent-mcp` path) requires Airbyte Cloud credentials.

### Credential setup

1. Go to [Airbyte Cloud](https://cloud.airbyte.com) and sign in.
2. Navigate to Settings, then Applications.
3. Create or find an application with access to your organization.
4. Note your Organization ID from the URL or settings page.
5. Find the connector instance IDs for Linear, Slack, or Gong in your workspace. Each connector has a UUID visible in the URL when you click on it.

Create your `.env` file:

```bash
cp .env.template .env
# Fill in Agent MCP values (org ID, client creds, connector IDs) manually.

# Or auto-populate native-MCP secrets from 1Password:
uv run agent-bench populate-env
```

The `.env.template` declares every accepted variable. Agent-MCP credentials
(org ID, client ID/secret, connector IDs) must be filled in manually.
Native-MCP credentials can be fetched from the `direct-connector-credentials`
1Password vault via `populate-env`.

### Authentication note

The MCP server uses an OIDC-proxy auth flow with one-time browser login. If you see a `401` error with "Client has no organization_admin permissions," verify that:

1. The `AIRBYTE_ORGANIZATION_ID` matches the org your application belongs to.
2. The application has `organization_admin` permissions on the Agent REST API.
3. You are using the correct client ID and secret pair for that specific organization.

Some Airbyte Cloud application credentials are scoped to a particular org. The same `client_id`/`client_secret` may fail for one org but succeed for another. The org ID must match the org that granted the application its permissions.

### Run all paths for a connector

```bash
uv run agent-bench run --scenarios linear --paths all --export-markdown linear-results.md
```

This runs agent-mcp (live or replay, see below) and native-mcp (replay) side by side.

### Recording agent-mcp from `mcp.airbyte.ai` (real MCP)

`agent-mcp` recordings come from real JSON-RPC calls to `mcp.airbyte.ai` so that token counts include the FastMCP envelope, server-side `select_fields` projection, response truncation, and compaction — what an agent actually consumes.

The MCP server uses an OIDC-proxy auth flow. There is no API-token shortcut; you must complete a one-time browser login. Tokens then refresh automatically until the FastMCP refresh token expires (~3 days of inactivity).

```bash
# 1. Once per machine (or whenever you see HTTP 401 during recording):
uv run agent-bench auth

# 2. Re-record agent-mcp scenarios for today:
uv run agent-bench record --path agent-mcp --date 2026-04-30

# Or a single connector:
uv run agent-bench record --path agent-mcp --connectors linear
```

The recorder reads each scenario's `paths.agent-mcp.tool_calls` block, calls `mcp__airbyte-agent__execute` over JSON-RPC, and writes `recording.json` files in the same shape `agent-bench` already replays.

### Interpreting live results

When `agent-mcp` runs in `--mode live`, token counts will vary as the underlying data changes. This is expected behavior, not a test failure.

The replay paths (agent-mcp and native-mcp) are deterministic. Their token totals should always match the committed recordings.

## Tier 3: Full Benchmark

The full benchmark covers all connectors, tasks, and paths. Use `agent-bench list` to see the current scenario matrix.

### Running what is available

```bash
# Linear: all paths
uv run agent-bench run --scenarios linear --paths all

# All connectors, agent-mcp replay
uv run agent-bench run --scenarios linear,slack,gong,salesforce,zendesk --paths agent-mcp
```

### Full export

The full export command is intentionally gated. It will fail if any replay recordings are missing:

```bash
uv run agent-bench run \
  --scenarios all \
  --paths all \
  --export-markdown artifacts/YYYY-MM-DD/final-scorecard.md \
  --export-charts artifacts/YYYY-MM-DD/final-charts
```

## Troubleshooting

### "Client has no organization_admin permissions" (HTTP 401)

The application credentials do not have `organization_admin` scope on the target org. Verify:

- The `AIRBYTE_ORGANIZATION_ID` matches the org your application was created in.
- The application has not been revoked or its permissions changed.
- You are not mixing credentials from different organizations.

### "missing recording at artifacts/..."

The requested replay file does not exist. Either:

- You are running a scenario or path whose recordings have not been committed yet.
- The artifacts directory was not included in your clone. Run `git status` to verify.

### Live agent-mcp token counts differ from the artifact

This is expected when running with `--mode live`. The live path returns current data; replay paths are the stable reference for comparison.

### HTTP 503 on Slack search

The Context Store preview may return 503 while indexing. This is a readiness issue, not a harness bug. See [issue #39](https://github.com/airbytehq/airbyte-agents-benchmarks/issues/39) for current Slack status.

### "Export blocked: required record-replay files are missing or stale"

The export gate prevents incomplete scorecards. Run with specific `--scenarios` and `--paths` flags to export only the cells you have recordings for:

```bash
uv run agent-bench run \
  --scenarios linear,slack,gong \
  --paths agent-mcp \
  --export-markdown partial-results.md
```

## Artifact Layout

Each benchmark run produces immutable artifacts under a dated directory:

```
artifacts/
  YYYY-MM-DD/
    linear-search-scenario/
      agent-mcp/
        recording.json
        recording-stats.json
      native-mcp/
        recording.json
        recording-stats.json
    gong-get-scenario/
      ...
    <report>.md          # filename varies by export command
    charts/
```

The [`latest_comparison_report/`](../latest_comparison_report/) directory at the repo root contains a symlinked `README.md` pointing to the most recent comparison report.

## CLI Reference

```text
agent-bench list             List available benchmark scenarios
agent-bench plan             Print MCP tool-call specs for record-replay paths
agent-bench run              Run the benchmark across selected scenarios and paths
agent-bench validate         Validate replay recordings before exporting
agent-bench compare          Generate a markdown comparison report from recording stats
agent-bench generate-stats   Generate recording-stats.json from existing recordings
agent-bench auth             One-time browser OAuth for mcp.airbyte.ai
agent-bench record           Record MCP responses for benchmark replay
agent-bench record-one       Save a single MCP tool-call response as a recording
```

The `plan`, `run`, and `validate` commands accept `--scenarios` and `--paths` filters. Pass connector names (e.g. `linear`) to `--scenarios` to select all scenarios for that connector, or pass specific scenario names (e.g. `linear-search,linear-get`). Use `--help` on any command for full options.

Export is blocked when recordings or cells have issues. See [METHODOLOGY.md](METHODOLOGY.md#export-gates) for the full list of export gates.

## Recording New Responses

```bash
uv run agent-bench plan --scenarios all --paths native-mcp,agent-mcp
```

For each Agent MCP connector, call `mcp__airbyte-agent__describe_connector` once before recording the planned `mcp__airbyte-agent__execute` call. Every execute item must include `select_fields`.

Save MCP responses with:

```bash
uv run agent-bench record-one \
  --path agent-mcp \
  --scenario linear-search \
  --tool mcp__airbyte-agent__execute \
  --args '{"items":[...]}' \
  --response-file /tmp/response.json \
  --reset
```

For Agent MCP, `--wall-ms` can be omitted when the response contains `execution_metadata.execution_time_ms`.
