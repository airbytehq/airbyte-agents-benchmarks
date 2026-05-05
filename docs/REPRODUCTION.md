# Reproducing the Benchmark

Video Walkthrough:
https://github.com/airbytehq/airbyte-agents-benchmarks/blob/main/docs/assets/benchmark-repro-walkthrough.mp4

This guide covers reproducing the Airbyte Agents benchmark results.
The repo ships with committed `recording-stats.json` files, so you can
generate comparison reports without any credentials or recordings.

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
uv run agent-bench --help
```

## Create New Benchmark Recordings (Optional)

Recording captures fresh MCP responses. Stats are generated
automatically after every successful recording.

### Credential setup

For **agent-mcp** recording (the default path), you need:

- `AIRBYTE_ORGANIZATION_ID` and connector IDs (e.g. `LINEAR_CONNECTOR_ID`) in `.env`
- A one-time OAuth login via `agent-bench auth` (see below)

For **emulated-mcp** recording (uses Sonar REST API), you additionally need:

- `AIRBYTE_CLIENT_ID` and `AIRBYTE_CLIENT_SECRET` from an Airbyte Cloud Application

To set up `AIRBYTE_CLIENT_ID`/`AIRBYTE_CLIENT_SECRET` for emulated-mcp:

1. Go to [Airbyte Cloud](https://app.airbyte.ai) and sign in.
2. Navigate to Settings, then Applications.
3. Create or find an application with access to your organization.
4. Note your Organization ID from the URL or settings page.
5. Find the connector instance IDs for Linear, Slack, or Gong in your workspace. Each connector has a UUID visible in the URL when you click on it.

Create your `.env` file:

```bash
cp .env.template .env
# Fill in Agent MCP values (org ID, connector IDs) manually.
```

> **Airbyte-internal:** Native-MCP credentials can be fetched from the
> `direct-connector-credentials` 1Password vault via `uv run agent-bench populate-env`.
> This requires `SONAR_CONNECTOR_CREDS_1PASS_TOKEN`.

### Recording prerequisites

Before recording `agent-mcp` scenarios, ensure:

1. **Connector credentials are configured.** Each connector you plan to record (e.g., Linear, Slack, Gong) must have valid credentials added in the [Agent Engine](https://docs.airbyte.com/ai-agents/mcp-server/). Users must [authenticate](https://docs.airbyte.com/ai-agents/platform/authenticate/) with each connected service.
2. **The context store has completed its initial sync.** Search-based scenarios depend on the [context store](https://docs.airbyte.com/ai-agents/entity-cache/), which must finish its first full data population before search results are available. You can check sync status in the Agent Engine UI under Connectors.

### Recording agent-mcp

`agent-mcp` recordings come from real JSON-RPC calls to `mcp.airbyte.ai`
so that token counts include the FastMCP envelope, server-side
field selection via `select_fields`, response truncation, and compaction.

The MCP server uses an OIDC-proxy auth flow. There is no API-token
shortcut; you must complete a one-time browser login. Tokens refresh
automatically until the refresh token expires (approximately 60 days).

```bash
# 1. Once per machine (or whenever you see HTTP 401 during recording):
uv run agent-bench auth

# 2. Record agent-mcp scenarios:
uv run agent-bench record --path agent-mcp

# Or a single connector:
uv run agent-bench record --path agent-mcp --connectors linear
```

### Recording native-mcp

Native MCP recordings use vendor-provided MCP servers. See
[THIRD_PARTY_MCP_SETUP.md](THIRD_PARTY_MCP_SETUP.md) for setup details.

```bash
uv run agent-bench record --path native-mcp --connectors linear
```

### Regenerating stats only

To regenerate `recording-stats.json` from existing `recording.json`
files without re-recording:

```bash
uv run agent-bench record --stats-only
```

> **Note:** This requires local `recording.json` files from a previous
> recording run. These files are gitignored and not included in a fresh
> clone — you must record at least once before `--stats-only` will work.

## Generate a Comparison Report (No Credentials)

The committed `recording-stats.json` files in `artifacts/YYYY-MM-DD/`
contain aggregate metrics (token counts, latency, record counts). Raw
`recording.json` files are gitignored and never committed.

```bash
uv run agent-bench compare
```

This reads the committed stats and produces a markdown comparison of
token efficiency across connectors.

## Troubleshooting

### "Client has no organization_admin permissions" (HTTP 401)

The application credentials do not have `organization_admin` scope on the target org. Verify:

- The `AIRBYTE_ORGANIZATION_ID` matches the org your application was created in.
- The application has not been revoked or its permissions changed.
- You are not mixing credentials from different organizations.

Some Airbyte Cloud application credentials are scoped to a particular org. The same `client_id`/`client_secret` may fail for one org but succeed for another.

### "missing recording at artifacts/..."

The requested replay file does not exist. Either:

- You are running a scenario or path whose recordings have not been committed yet.
- The artifacts directory was not included in your clone. Run `git status` to verify.

### HTTP 503 on Slack search

The Context Store preview may return 503 while indexing. This is a readiness issue, not a harness bug. See [issue #39](https://github.com/airbytehq/airbyte-agents-benchmarks/issues/39) for current Slack status.

## Artifact Layout

Each recording run produces artifacts under a dated directory:

```
artifacts/
  YYYY-MM-DD/
    linear-search-scenario/
      agent-mcp/
        recording.json          # gitignored
        recording-stats.json    # committed
      native-mcp/
        recording.json          # gitignored
        recording-stats.json    # committed
    gong-get-scenario/
      ...
```

The [`latest_comparison_report/`](../latest_comparison_report/) directory at the repo root contains a symlinked `README.md` pointing to the most recent comparison report.

## CLI Reference

```text
agent-bench compare       Generate a markdown comparison report from recording stats
agent-bench auth          One-time browser OAuth for mcp.airbyte.ai
agent-bench record        Record MCP responses and auto-generate recording-stats.json
agent-bench record-one    Save a single MCP tool-call response as a recording
agent-bench populate-env  Populate .env from 1Password credentials
```

Use `--help` on any command for full options.
