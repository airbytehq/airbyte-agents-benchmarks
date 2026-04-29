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
uv run agent-bench validate --scenarios linear,granola --paths native-mcp,agent-mcp
```

Expected output: `recordings ok`

### Run replay paths

```bash
uv run agent-bench run \
  --scenarios linear,granola \
  --paths agent-mcp,native-mcp \
  --export-markdown results.md
```

Expected token totals (deterministic from recordings):

| Path | Linear | Granola | Total |
|---|---:|---:|---:|
| Agent MCP | 3,744 | 1,485 | 5,229 |
| Native MCP | 8,510 | 5,118 | 13,628 |

These match the committed April 24 artifact exactly.

## Tier 2: Live SDK Path (Requires Credentials)

The REST Baseline path makes live API calls via the `airbyte-agent-sdk` package. You need Airbyte Cloud credentials.

### Credential setup

1. Go to [Airbyte Cloud](https://cloud.airbyte.com) and sign in.
2. Navigate to Settings, then Applications.
3. Create or find an application with access to your organization.
4. Note your Organization ID from the URL or settings page.
5. Find the connector instance IDs for Linear, Granola, or Slack in your workspace. Each connector has a UUID visible in the URL when you click on it.

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
GRANOLA_CONNECTOR_ID=your-granola-source-uuid
SLACK_CONNECTOR_ID=your-slack-source-uuid
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

# Multiple connectors
uv run agent-bench run --scenarios linear,slack --paths agent-sdk
```

### Run all paths for a connector

```bash
uv run agent-bench run --scenarios linear --paths all --export-markdown linear-results.md
```

This runs agent-sdk (live), agent-mcp (replay), and native-mcp (replay) side by side.

### Interpreting live results

The REST Baseline path is live, so token counts will vary as the underlying data changes. The committed April 24 artifact recorded 66,587 total Baseline tokens for Linear and Granola. A verification run on April 27 showed 53,000 tokens because the Linear issue data had changed. This is expected behavior, not a test failure.

The replay paths (agent-mcp and native-mcp) are deterministic. Their token totals should always match the committed artifact (5,229 and 13,628 for Linear and Granola).

## Tier 3: Full Benchmark

The full benchmark covers all connectors, tasks, and paths. Use `agent-bench list` to see the current scenario matrix.

### Current status

| Connector | agent-sdk | agent-mcp | native-mcp |
|---|---|---|---|
| Linear | Available | Recordings committed | Recordings committed |
| Granola | Requires Granola connector in your org | Recordings committed | Recordings committed |
| Slack | Available | No recordings yet | No recordings yet |

Slack replay recordings are not yet committed. The Slack search task was returning HTTP 503 from the Context Store during the recording window. See `docs/SLACK_STATUS.md` for the completion path.

### Running what is available

```bash
# Linear: all paths
uv run agent-bench run --scenarios linear --paths all

# Granola: replay only (no SDK unless you have a Granola connector)
uv run agent-bench run --scenarios granola --paths agent-mcp,native-mcp

# Slack: SDK only (requires Slack connector in your org)
uv run agent-bench run --scenarios slack --paths agent-sdk
```

### Full export

The full export command is intentionally gated. It will fail if any replay recordings are missing:

```bash
uv run agent-bench run \
  --scenarios all \
  --paths all \
  --export-markdown artifacts/2026-04-24/final-scorecard.md \
  --export-charts artifacts/2026-04-24/final-charts
```

## Troubleshooting

### "Client has no organization_admin permissions" (HTTP 401)

The application credentials do not have `organization_admin` scope on the target org. Verify:

- The `AIRBYTE_ORGANIZATION_ID` matches the org your application was created in.
- The application has not been revoked or its permissions changed.
- You are not mixing credentials from different organizations.

### "missing recording at artifacts/..."

The requested replay file does not exist. Either:

- You are running a scenario or path whose recordings have not been committed yet (Slack).
- The artifacts directory was not included in your clone. Run `git status` to verify.

### REST Baseline token counts differ from the artifact

This is expected. The REST Baseline path is live and returns current data. The committed artifact reflects data as of April 24, 2026. Replay paths are the stable reference for comparison.

### HTTP 503 on Slack search

The Context Store preview may return 503 while indexing. This is a readiness issue, not a harness bug. Check `docs/SLACK_STATUS.md` for current status.

### "Export blocked: required record-replay files are missing or stale"

The export gate prevents incomplete scorecards. Run with specific `--scenarios` and `--paths` flags to export only the cells you have recordings for:

```bash
uv run agent-bench run \
  --scenarios linear,granola \
  --paths agent-mcp,native-mcp \
  --export-markdown partial-results.md
```

## CLI Reference

```bash
uv run agent-bench list              # Show all scenarios and connector IDs
uv run agent-bench plan              # Show recording plan for replay paths
uv run agent-bench run               # Run benchmark cells
uv run agent-bench validate          # Validate replay recordings
```

All commands accept `--scenarios` and `--paths` filters. Use `--help` on any command for full options.
