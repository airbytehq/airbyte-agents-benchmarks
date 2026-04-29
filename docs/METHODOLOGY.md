# Methodology

This repository packages the Airbyte Agents launch benchmark harness and the April 24, 2026 interim result set.

The benchmark compares three ways an agent can fetch the same business data:

| Path | What it measures | Payload consumed by the agent |
|---|---|---|
| REST Baseline (via SDK) | Token cost of consuming the provider's full REST API response | Full typed records as returned by the third-party service (Linear, Granola, etc.) — see [below](#agent-sdk-as-rest-baseline) |
| Agent MCP | Hosted Airbyte Platform MCP calls with mandatory `select_fields` | Narrow typed JSON selected by the MCP call |
| Native MCP | Vendor-native MCP server calls | Connector-specific MCP responses, which may be JSON, text, or markdown-like |

## Scenario Shape

Each connector has three named scenarios, one per task type:

| Action | Purpose |
|---|---|
| `search` | Find records by a keyword or filter |
| `get` | Fetch one known record by ID |
| `list` | Fetch a page of records |

Scenarios are named `{connector}-{action}` (e.g., `linear-search`, `granola-get`) and stored as YAML files in `src/agent_bench/scenarios/`.

## Token Counting

Token counts are computed with `tiktoken` using the `cl100k_base` encoding. The harness measures the raw response payload that the agent would consume for each path, not a cleaned summary.

This means:

- REST Baseline token counts represent the cost of consuming the full records that the third-party provider's REST API returns. The Airbyte connector fetches these records from the provider (e.g., Linear's API, Granola's API) and passes them through without modification. The SDK adds no transformation, so the token count is equivalent to what an agent would see if it called the provider's REST API directly.
- Agent MCP token counts include the MCP response after `select_fields` narrows the returned fields.
- Native MCP token counts include the recorded native MCP tool response, preserving its connector-specific shape.

**Important:** The SDK path returns all fields (30-50+ per record) while the Agent MCP path applies `select_fields` to return only 6-10 fields. Token ratios between these paths therefore primarily reflect the effect of field projection, not transport or protocol differences. A fair protocol comparison requires applying equivalent field projection on the SDK side.

## Payload Bytes

Payload bytes are measured as the UTF-8 byte length of the JSON-encoded response payload. This gives a transport-adjacent size comparison alongside the token count.

Bytes and tokens can diverge because tokenization is model-specific, while byte count is literal payload size.

## Timing

Timing is path-specific:

- REST Baseline (via SDK) uses client-side wall clock around the SDK call.
- Agent MCP uses `execution_metadata.execution_time_ms` from the MCP response.
- Native MCP timing is not captured by the harness. Native MCP replay rows show `0` latency and should be read as unmeasured, not instant.

## Record-Replay Paths

`agent-mcp` and `native-mcp` are record-replay paths. Their recordings live in `artifacts/{date}/{scenario}-scenario/{path}/recording.json`.

The validation command checks that required replay files exist and that Agent MCP recordings are not stale:

```bash
uv run agent-bench validate --scenarios linear,granola --paths native-mcp,agent-mcp
```

Agent MCP recordings must include:

- `mcp__airbyte-agent__execute`
- `select_fields`
- `execution_metadata.execution_time_ms`
- `wall_clock_ms` copied from execution metadata

## Export Gates

Markdown and chart exports are blocked when:

- required replay recordings are missing,
- Agent MCP recordings are stale or missing `select_fields`,
- any benchmark cell errors or is skipped,
- REST Baseline and Agent MCP record counts differ for the same task.

The April 24 artifact is intentionally an interim Linear+Granola export because Slack search was not ready.

## Agent SDK as REST Baseline

The `agent-sdk` path measures the token cost of consuming the provider's full REST API response. The Airbyte connector calls the provider (Linear, Granola, Slack), returns the same records, and the SDK passes them through without transformation. The benchmark counts tokens on `json.dumps(records)` via `tiktoken` — the same records an agent would get calling the provider directly.

**Output token overhead: zero.** Neither the connector nor the SDK modifies the provider's records. The benchmark extracts the record list from the response and token-counts it identically to a direct provider call.

**Input token overhead: negligible.** The SDK replaces per-provider auth and endpoint setup with a single `executor.execute(entity, action, params)` call. Request tokens are small relative to the response payload.

## Reproducibility Caveat

The SDK path is live. It can drift when the underlying connector data changes. The April 24 scorecard committed under `artifacts/2026-04-24/scorecard.md` is the frozen launch artifact for the 66,587 SDK token total.

As of the April 27, 2026 verification run, Linear+Granola completed successfully but the live SDK token total was 53,000 because current Linear payloads had changed. Agent MCP and Native MCP replay totals remained 5,229 and 13,628.

