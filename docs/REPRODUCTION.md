# Reproducing the Benchmark

This guide walks through reproducing the Airbyte Agents launch benchmark results from scratch. It covers three tiers of reproduction, from no credentials required to full live runs.

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

## Tier 1: Replay-Only (No Credentials)

The committed recordings in `artifacts/YYYY-MM-DD/` make the record-replay paths fully deterministic. You can validate and run them without any API credentials.

### Run tests

```bash
uv run pytest -q
```

All 5 tests should pass.

### Validate recordings

```bash
uv run agent-bench validate --scenarios linear,slack,gong,salesforce,zendesk --paths agent-mcp
```

Expected output: `recordings ok`

### Run replay paths

```bash
uv run agent-bench run \
  --scenarios linear,slack,gong,salesforce,zendesk \
  --paths agent-mcp \
  --export-markdown results.md
```

Token totals are deterministic from the committed recordings.

## Tier 2: Live SDK Path (Requires Credentials)

The REST Baseline path makes live API calls via the `airbyte-agent-sdk` package. You need Airbyte Cloud credentials.

### Credential setup

1. Go to [Airbyte Cloud](https://cloud.airbyte.com) and sign in.
2. Navigate to Settings, then Applications.
3. Create or find an application with access to your organization.
4. Note your Organization ID from the URL or settings page.
5. Find the connector instance IDs for Linear, Slack, or Gong in your workspace. Each connector has a UUID visible in the URL when you click on it.

Create your `.env` file:

```bash
cp .env.example .env
```

Fill in the values:

```bash
AIRBYTE_ORGANIZATION_ID=your-org-uuid
AIRBYTE_CLIENT_ID=your-client-id
AIRBYTE_CLIENT_SECRET=your-client-secret
LINEAR_CONNECTOR_ID=your-linear-source-uuid
SLACK_CONNECTOR_ID=your-slack-source-uuid
GONG_CONNECTOR_ID=your-gong-source-uuid
SALESFORCE_CONNECTOR_ID=your-salesforce-source-uuid
ZENDESK_CONNECTOR_ID=your-zendesk-source-uuid
```

### Authentication note

The SDK authenticates via `POST https://api.airbyte.ai/api/v1/account/applications/token`. It sends the `X-Organization-Id` header alongside the client credentials. If you see a `401` error with "Client has no organization_admin permissions," verify that:

1. The `AIRBYTE_ORGANIZATION_ID` matches the org your application belongs to.
2. The application has `organization_admin` permissions on the Agent REST API.
3. You are using the correct client ID and secret pair for that specific organization.

Some Airbyte Cloud application credentials are scoped to a particular org. The same `client_id`/`client_secret` may fail for one org but succeed for another. The `X-Organization-Id` header must match the org that granted the application its permissions.

### Run the REST Baseline path

```bash
# Single connector
uv run agent-bench run --scenarios linear --paths agent-sdk

# All five connectors
uv run agent-bench run --scenarios linear,slack,gong,salesforce,zendesk --paths agent-sdk
```

### Run all paths for a connector

```bash
uv run agent-bench run --scenarios linear --paths all --export-markdown linear-results.md
```

This runs agent-sdk (live), agent-mcp (replay), and native-mcp (replay) side by side.

### Interpreting live results

The REST Baseline path is live, so token counts will vary as the underlying data changes. This is expected behavior, not a test failure.

The replay paths (agent-mcp and native-mcp) are deterministic. Their token totals should always match the committed recordings.

## Tier 3: Full Benchmark

The full benchmark covers all connectors, tasks, and paths. Use `agent-bench list` to see the current scenario matrix.

### Running what is available

```bash
# Linear: all paths
uv run agent-bench run --scenarios linear --paths all

# All five connectors, agent-mcp replay
uv run agent-bench run --scenarios linear,slack,gong,salesforce,zendesk --paths agent-mcp

# All five connectors, live SDK
uv run agent-bench run --scenarios linear,slack,gong,salesforce,zendesk --paths agent-sdk
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

### REST Baseline token counts differ from the artifact

This is expected. The REST Baseline path is live and returns current data. Replay paths are the stable reference for comparison.

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

A symlink at [`latest-benchmark-result-report.md`](../latest-benchmark-result-report.md) in the repo root points to the most recent report.

## CLI Reference

```text
agent-bench list             List available benchmark scenarios
agent-bench plan             Print MCP tool-call specs for record-replay paths
agent-bench run              Run the benchmark across selected scenarios and paths
agent-bench validate         Validate replay recordings before exporting
agent-bench compare          Generate a markdown comparison report from recording stats
agent-bench generate-stats   Generate recording-stats.json from existing recordings
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
uv run python scripts/record_response.py \
  --path agent-mcp \
  --scenario linear-search \
  --tool mcp__airbyte-agent__execute \
  --args '{"items":[...]}' \
  --response-file /tmp/response.json \
  --reset
```

For Agent MCP, `--wall-ms` can be omitted when the response contains `execution_metadata.execution_time_ms`.
