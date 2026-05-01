# Methodology

This repository packages the Airbyte Agents benchmark harness and result artifacts.

The benchmark compares three ways an agent can fetch the same business data:

| Path | What it measures | Payload consumed by the agent |
|---|---|---|
| REST Baseline (via SDK) | Token cost of consuming the provider's full REST API response | Full typed records as returned by the third-party service (Linear, Slack, etc.) — see [below](#agent-sdk-as-rest-baseline) |
| Agent MCP | Hosted Airbyte Platform MCP calls with mandatory `select_fields` | Narrow typed JSON selected by the MCP call |
| Native MCP | Vendor-native MCP server calls | Connector-specific MCP responses, which may be JSON, text, or markdown-like |

## Scenario Shape

Scenarios are organized by task type. Not every connector implements every action:

| Action | Purpose |
|---|---|
| `search` | Find records by a keyword or filter |
| `get` | Fetch one known record by ID |
| `list-all` | Fetch all records with automatic pagination |

Single-task scenarios are named `{connector}-{action}` (e.g., `linear-search`, `zendesk-get`) and stored as YAML files in `src/agent_bench/scenarios/`.

### Multi-Step Scenarios

Some scenarios chain multiple tool calls across different connectors to represent cross-system workflows. For example, `gong-to-salesforce-zendesk-lookup` searches Gong for calls, then looks up associated accounts in Salesforce and open tickets in Zendesk.

Two properties of multi-step scenarios are important for understanding the benchmark results:

1. **The harness is not an LLM agent loop.** The scenario YAML defines the MCP tool-call sequence and parameters that would be used by an agent. Live MCP calls happen at recording time to capture canonical request/response artifacts; benchmark runs then deterministically replay the recorded responses. The harness does not wrap calls in an LLM, and it does not make decisions about what to call next. This is intentional: replayed tool interactions produce deterministic results, which is a requirement for stable, reproducible comparisons. The calls are "real" in the sense that the recordings come from the same tools, parameters, and response formats that an LLM-based agent would use — the harness simply removes the LLM inference step and reuses the captured outputs so that measurements reflect data-path efficiency, not model behavior.

2. **Subsequent step inputs are statically seeded.** In a multi-step scenario, the inputs to later steps (e.g., which account names are passed to the Salesforce lookup) are fixed values captured at recording time and reused during benchmark replay. The harness does not dynamically pass the output of step 1 as input to step 2 at benchmark runtime. This ensures that every run of the benchmark replays the same tool interactions regardless of when it runs. The specific input values do not affect the benchmark's evaluation methodology — the benchmark measures token efficiency of the response payloads, not the relevance of the query parameters.

## Token Counting

Token counts are computed with `tiktoken` using the `cl100k_base` encoding. The harness measures the raw response payload that the agent would consume for each path, not a cleaned summary.

This means:

- REST Baseline token counts represent the cost of consuming the full records that the third-party provider's REST API returns. The Airbyte connector fetches these records from the provider (e.g., Linear's API, Slack's API) and passes them through without modification. The SDK adds no transformation, so the token count is equivalent to what an agent would see if it called the provider's REST API directly.
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
uv run agent-bench validate --scenarios linear,slack --paths native-mcp,agent-mcp
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

## Why Token Reduction Matters

Reducing the token count of tool responses affects LLM-based agents in three dimensions:

- **Latency.** LLM inference time scales with input token count. A tool response with 200 tokens is processed significantly faster than one with 15,000 tokens. In agentic workflows where multiple tool calls happen sequentially, these savings compound across each step.
- **Cost.** LLM APIs charge per token for both input and output. Every token in a tool response is an input token the LLM must consume on the next turn. Reducing response payload sizes directly reduces the per-call cost of agentic workflows.
- **Context window pressure.** LLMs have finite context windows. Large tool responses consume a disproportionate share of available context, leaving less room for conversation history, system instructions, and subsequent tool calls. As the context fills, the model's ability to reason accurately degrades — an effect sometimes called "lost in the middle." Compact responses preserve context budget for what matters.

The benchmark quantifies these differences by measuring raw token counts on identical data operations across paths.

## Agent SDK as REST Baseline

The `agent-sdk` path measures the token cost of consuming the provider's full REST API response. The Airbyte connector calls the provider (Linear, Slack, Gong), returns the same records, and the SDK passes them through without transformation. The benchmark counts tokens on `json.dumps(records)` via `tiktoken` — the same records an agent would get calling the provider directly.

**Output token overhead: zero.** Neither the connector nor the SDK modifies the provider's records. The benchmark extracts the record list from the response and token-counts it identically to a direct provider call.

**Input token overhead: negligible.** The SDK replaces per-provider auth and endpoint setup with a single `executor.execute(entity, action, params)` call. Request tokens are small relative to the response payload.


