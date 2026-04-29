# Airbyte Agents Benchmarks

A three-way benchmark comparing how AI agents access business data through Airbyte Agents. The harness measures token cost, payload size, and latency across three paths for the same tasks.

| Path | Slug | Description |
|---|---|---|
| REST Baseline (via SDK) | `agent-sdk` | Token cost of consuming the provider's full REST API response. The Airbyte connector fetches records from the third-party provider and passes them through unmodified — token counts are equivalent to calling the provider directly. See [Methodology](docs/METHODOLOGY.md#agent-sdk-as-rest-baseline). |
| Agent MCP | `agent-mcp` | Record-replay of the hosted Airbyte Platform MCP with mandatory `select_fields` |
| Native MCP | `native-mcp` | Record-replay of vendor-native MCP server responses |

Each connector scenario runs three tasks: **search**, **get** (single record by ID), and **list** (paginated bulk fetch).

The current reproducible artifact is an interim Linear + Granola scorecard with 18 of 27 cells complete. Slack is excluded until Context Store search is ready (see `docs/SLACK_STATUS.md`).

## Quick Start (No Credentials)

The `native-mcp` replay path can be validated and run using only the committed recordings, with no API access or environment variables required.

```bash
git clone https://github.com/airbytehq/airbyte-agents-benchmarks.git
cd airbyte-agents-benchmarks
uv sync
uv run pytest -q
uv run agent-bench run \
  --connectors linear,granola \
  --paths agent-mcp,native-mcp \
  --export-markdown results.md
```

> **Note:** Validating `agent-mcp` recordings requires env vars because the validator checks `connector_id` consistency with your configured environment. If you only want to inspect the replay data without credentials, validate the `native-mcp` path alone or read the recordings directly.

See [docs/REPRODUCTION.md](docs/REPRODUCTION.md) for the full reproduction guide, including live SDK setup, credential acquisition, and troubleshooting.

## Headline Results (April 24 Artifact)

Agent MCP used **12.7x fewer tokens** than the REST Baseline and **2.6x fewer tokens** than native vendor MCPs across the included Linear + Granola cells.

See [docs/RESULTS.md](docs/RESULTS.md) for the full numbers, connector-level breakdowns, and safe claims.

## Repository Contents

| Path | Description |
|---|---|
| `src/agent_bench/` | Benchmark harness and CLI |
| `src/agent_bench/scenarios/*.yaml` | Scenario definitions (Linear, Granola, Slack) |
| `tests/` | Unit tests for scenarios, validation, and scorecard rendering |
| `scripts/record_response.py` | Helper for saving replay recordings |
| `assets/recordings/` | Committed Linear and Granola replay recordings |
| `artifacts/2026-04-24/` | Scorecard, charts, and supporting deck artifact |
| `docs/REPRODUCTION.md` | Step-by-step reproduction guide with troubleshooting |
| `docs/METHODOLOGY.md` | Measurement details and design choices |
| `docs/RESULTS.md` | Current numbers and safe claims |
| `docs/CTO_BRIEF.md` | Executive-facing summary and caveats |
| `docs/SLACK_STATUS.md` | Slack blocker and completion path |
| `docs/THIRD_PARTY_MCP_SETUP.md` | Installation and configuration guide for third-party MCP servers (Linear, Granola, Slack) |

## CLI Reference

```text
agent-bench list       List available benchmark scenarios
agent-bench plan       Print MCP tool-call specs for record-replay paths
agent-bench run        Run the benchmark across selected connectors and paths
agent-bench validate   Validate replay recordings before exporting
```

All commands accept `--connectors` and `--paths` filters. Use `--help` on any command for full options.

Export is blocked when recordings or cells have issues. See [docs/METHODOLOGY.md](docs/METHODOLOGY.md#export-gates) for the full list of export gates.

## Recording New Responses

```bash
uv run agent-bench plan --connectors all --paths native-mcp,agent-mcp
```

For each Agent MCP connector, call `mcp__airbyte-agent__describe_connector` once before recording the planned `mcp__airbyte-agent__execute` call. Every execute item must include `select_fields`.

Save MCP responses with:

```bash
uv run python scripts/record_response.py \
  --path agent-mcp \
  --scenario linear \
  --action search \
  --tool mcp__airbyte-agent__execute \
  --args '{"items":[...]}' \
  --response-file /tmp/response.json \
  --reset
```

For Agent MCP, `--wall-ms` can be omitted when the response contains `execution_metadata.execution_time_ms`.

## Further Reading

- [Reproduction Guide](docs/REPRODUCTION.md) — end-to-end walkthrough from clone to results
- [Methodology](docs/METHODOLOGY.md) — measurement design, token counting, timing
- [Results](docs/RESULTS.md) — current numbers, safe claims, and caveats
- [CTO Brief](docs/CTO_BRIEF.md) — executive-facing summary
- [Slack Status](docs/SLACK_STATUS.md) — Slack blocker and completion path
- [Third-Party MCP Setup](docs/THIRD_PARTY_MCP_SETUP.md) — install and configure Linear, Granola, and Slack MCP servers
