# Agent Engine Launch Benchmark

Private handoff package for the Agent Engine Context Store launch benchmark.

The benchmark compares three paths:

- `ae-sdk`: live `airbyte-agent-sdk` calls against Agent Engine.
- `ae-mcp`: record-replay of the hosted Airbyte Platform MCP with mandatory `select_fields`.
- `claude`: record-replay of Claude cloud MCP tool responses.

The planned scenarios are Slack, Linear, and Granola, each with search, get, and list tasks. The current reproducible artifact is an interim Linear+Granola scorecard with 18 of 27 cells complete.

## Contents

- `src/agent_bench/`: benchmark harness and CLI.
- `tests/`: unit tests for scenarios, validation, and scorecard rendering.
- `scripts/record_response.py`: helper for saving replay recordings.
- `assets/recordings/`: current Linear and Granola replay recordings.
- `artifacts/2026-04-24/`: scorecard, charts, and supporting deck artifact.
- `docs/METHODOLOGY.md`: measurement details.
- `docs/RESULTS.md`: current numbers and safe claims.
- `docs/CTO_BRIEF.md`: executive-facing summary and caveats.
- `docs/SLACK_STATUS.md`: Slack blocker and completion path.
- `docs/REPRODUCTION.md`: step-by-step reproduction guide with troubleshooting.

## Quick Start (No Credentials)

The replay paths are fully deterministic from committed recordings. You can validate the benchmark without any API credentials:

```bash
uv sync
uv run pytest -q
uv run agent-bench run --connectors linear,granola --paths ae-mcp,claude --export-markdown results.md
```

See `docs/REPRODUCTION.md` for the full reproduction guide, including live SDK setup and troubleshooting.

## Setup

```bash
cp .env.example .env
# Fill AIRBYTE_ORGANIZATION_ID, AIRBYTE_CLIENT_ID, AIRBYTE_CLIENT_SECRET,
# LINEAR_CONNECTOR_ID, GRANOLA_CONNECTOR_ID, SLACK_CONNECTOR_ID.

uv run agent-bench list
```

Required environment variables:

- `AIRBYTE_ORGANIZATION_ID`
- `AIRBYTE_CLIENT_ID`
- `AIRBYTE_CLIENT_SECRET`
- `SLACK_CONNECTOR_ID`
- `LINEAR_CONNECTOR_ID`
- `GRANOLA_CONNECTOR_ID`

## Validation

```bash
uv run pytest -q
uv run agent-bench validate --connectors linear,granola --paths claude,ae-mcp
```

Expected validation result:

```text
recordings ok
```

## Reproduce Current Scope

```bash
uv run agent-bench run \
  --connectors linear,granola \
  --paths all \
  --export-markdown artifacts/2026-04-24/scorecard.md \
  --export-charts artifacts/2026-04-24/charts
```

Committed April 24 artifact totals:

- Agent Engine MCP: `5,229`
- SDK/API path: `66,587`
- Claude MCP: `13,628`
- Agent Engine MCP vs SDK/API: `12.7x` fewer tokens
- Agent Engine MCP vs Claude MCP: `2.6x` fewer tokens

The Agent Engine SDK/API path is live. Re-running can change SDK/API totals as source data changes. The committed April 24 scorecard is the frozen launch artifact; the replay paths (`ae-mcp` and `claude`) are deterministic from `assets/recordings/`.

## Full 27-Cell Export

Full export is intentionally blocked until Slack search and Slack MCP/Claude recordings are ready:

```bash
uv run agent-bench run \
  --connectors all \
  --paths all \
  --export-markdown artifacts/2026-04-24/final-scorecard.md \
  --export-charts artifacts/2026-04-24/final-charts
```

See `docs/SLACK_STATUS.md` before running or publishing the full scorecard.

## Recording Plan

```bash
uv run agent-bench plan --connectors all --paths claude,ae-mcp
```

For each Agent Engine MCP connector, call `mcp__airbyte-agent__describe_connector` once before recording the planned `mcp__airbyte-agent__execute` call. Every execute item must include `select_fields`.

Save MCP responses with:

```bash
uv run python scripts/record_response.py \
  --path ae-mcp \
  --scenario linear \
  --action search \
  --tool mcp__airbyte-agent__execute \
  --args '{"items":[...]}' \
  --response-file /tmp/response.json \
  --reset
```

For Agent Engine MCP, `--wall-ms` can be omitted when the response contains `execution_metadata.execution_time_ms`.
