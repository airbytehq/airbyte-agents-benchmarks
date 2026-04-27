# Methodology

This repository packages the Agent Engine launch benchmark harness and the April 24, 2026 interim result set.

The benchmark compares three ways an agent can fetch the same business data:

| Path | What it measures | Payload consumed by the agent |
|---|---|---|
| Agent Engine SDK/API | Direct `airbyte-agent-sdk` calls to Agent Engine | Full typed records returned by the SDK |
| Agent Engine MCP | Hosted Airbyte Platform MCP calls with mandatory `select_fields` | Narrow typed JSON selected by the MCP call |
| Claude cloud MCP | Anthropic-hosted connector MCP calls | Connector-specific MCP responses, which may be JSON, text, or markdown-like |

## Scenario Shape

Each connector has three tasks:

| Task | Purpose |
|---|---|
| `search` | Find records by a keyword or filter |
| `get` | Fetch one known record by ID |
| `list` | Fetch a page of records |

The current scenarios live in `src/agent_bench/scenarios/`:

- `linear.yaml`
- `granola.yaml`
- `slack.yaml`

## Token Counting

Token counts are computed with `tiktoken` using the `cl100k_base` encoding. The harness measures the raw response payload that the agent would consume for each path, not a cleaned summary.

This means:

- SDK/API token counts include full record bodies returned by `airbyte-agent-sdk`.
- Agent Engine MCP token counts include the MCP response after `select_fields` narrows the returned fields.
- Claude MCP token counts include the recorded Claude MCP tool response, preserving its connector-specific shape.

## Payload Bytes

Payload bytes are measured as the UTF-8 byte length of the JSON-encoded response payload. This gives a transport-adjacent size comparison alongside the token count.

Bytes and tokens can diverge because tokenization is model-specific, while byte count is literal payload size.

## Timing

Timing is path-specific:

- Agent Engine SDK/API uses client-side wall clock around the SDK call.
- Agent Engine MCP uses `execution_metadata.execution_time_ms` from the MCP response.
- Claude cloud MCP timing is not captured by the harness. Claude replay rows show `0` latency and should be read as unmeasured, not instant.

## Record-Replay Paths

`ae-mcp` and `claude` are record-replay paths. Their recordings live in `assets/recordings/`.

The validation command checks that required replay files exist and that Agent Engine MCP recordings are not stale:

```bash
uv run agent-bench validate --connectors linear,granola --paths claude,ae-mcp
```

Agent Engine MCP recordings must include:

- `mcp__airbyte-agent__execute`
- `select_fields`
- `execution_metadata.execution_time_ms`
- `wall_clock_ms` copied from execution metadata

## Export Gates

Markdown and chart exports are blocked when:

- required replay recordings are missing,
- Agent Engine MCP recordings are stale or missing `select_fields`,
- any benchmark cell errors or is skipped,
- Agent Engine SDK and Agent Engine MCP record counts differ for the same task.

The April 24 artifact is intentionally an interim Linear+Granola export because Slack search was not ready.

## Reproducibility Caveat

The SDK/API path is live. It can drift when the underlying connector data changes. The April 24 scorecard committed under `artifacts/2026-04-24/scorecard.md` is the frozen launch artifact for the 66,587 SDK/API token total.

As of the April 27, 2026 verification run, Linear+Granola completed successfully but the live SDK/API token total was 53,000 because current Linear payloads had changed. Agent Engine MCP and Claude MCP replay totals remained 5,229 and 13,628.
