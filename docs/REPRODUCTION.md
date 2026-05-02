# Reproducing the Benchmark

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

## Generate a Comparison Report (No Credentials)

The committed `recording-stats.json` files in `artifacts/YYYY-MM-DD/`
contain aggregate metrics (token counts, latency, record counts). Raw
`recording.json` files are gitignored and never committed.

```bash
uv run agent-bench compare
```

This reads the committed stats and produces a markdown comparison of
token efficiency across connectors.

## Recording (Optional)

Recording captures fresh MCP responses. Stats are generated
automatically after every successful recording.

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

### Recording agent-mcp

`agent-mcp` recordings come from real JSON-RPC calls to `mcp.airbyte.ai`
so that token counts include the FastMCP envelope, server-side
`select_fields` projection, response truncation, and compaction.

The MCP server uses an OIDC-proxy auth flow. There is no API-token
shortcut; you must complete a one-time browser login. Tokens refresh
automatically until the refresh token expires (~3 days of inactivity).

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

To regenerate `recording-stats.json` from existing recordings without
re-recording:

```bash
uv run agent-bench record --stats-only
```

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
