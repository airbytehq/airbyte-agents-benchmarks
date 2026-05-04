# Methodology

This repository packages the Airbyte Agents benchmark harness and result artifacts.

The benchmark compares two ways an agent can fetch the same business data:

| Path | What it measures | Payload consumed by the agent |
|---|---|---|
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

   Each multi-step scenario YAML records the provenance of its seed values (which step they came from, when they were captured, and from which path's response). The seeds are intentionally identical across both paths so neither side gets a chaining shortcut the other lacks.

   **Seeds are injected via environment variables, not committed values.** Multi-step scenario YAMLs reference seeds with `${VAR}` placeholders (e.g., `${CUSTOMER_1}`, `${CUSTOMER_2}`, `${CUSTOMER_3}` in `gong-to-salesforce-zendesk-lookup`). The recorder substitutes these from your `.env` at run time. **You must set these env vars** to names/IDs that exist in your own workspace before running the scenario — otherwise both paths will faithfully record empty results. The values can be anything; the benchmark measures payload size, not which records you query. See `.env.template` for the required vars per scenario.

#### What multi-step scenarios do *not* measure

The deterministic, no-LLM design has explicit limits that readers should keep in mind when interpreting cross-connector results:

- **Chain-reasoning cost is not measured.** In a real agent loop, the LLM consumes Step 1's full response into its context, generates an intermediate plan, and formats Step 2's call. Those input/output tokens scale with response size — a large native-mcp Step 1 response makes every subsequent decision more expensive. The benchmark only counts response-payload tokens, so the real-world delta in favor of smaller payloads is likely *larger* than what we report.
- **Intermediate parsing / normalization is not measured.** Mapping a Gong call title to a Salesforce account name involves real work (case folding, fuzzy matching, schema mismatch handling). By using seed values directly, we skip this; both paths benefit equally from the skip, but the absolute end-to-end cost of the workflow is understated.
- **The benchmark is not an end-to-end agent benchmark.** It measures the data-path delta between two ways of fetching the same business data. It does not measure how well an LLM can plan a multi-step workflow, how often it gets stuck, or how many tokens it spends on tool-formatting. A complementary live-LLM benchmark would be needed to quantify those.

## Token Counting

Token counts are computed with `tiktoken` using the `cl100k_base` encoding. The harness measures the raw response payload that the agent would consume for each path, not a cleaned summary.

This means:

- Agent MCP token counts include the MCP response after `select_fields` narrows the returned fields.
- Native MCP token counts include the recorded native MCP tool response, preserving its connector-specific shape.

## Payload Bytes

Payload bytes are measured as the UTF-8 byte length of the JSON-encoded response payload. This gives a transport-adjacent size comparison alongside the token count.

Bytes and tokens can diverge because tokenization is model-specific, while byte count is literal payload size.

## Timing

Timing is path-specific:

- Agent MCP uses `execution_metadata.execution_time_ms` from the MCP response.
- Native MCP timing is not captured by the harness. Native MCP replay rows show `0` latency and should be read as unmeasured, not instant.

## Record-Replay Paths

`agent-mcp` and `native-mcp` are record-replay paths. Their recordings live in `artifacts/{date}/{scenario}-scenario/{path}/recording.json`.

Agent MCP recordings must include:

- `mcp__airbyte-agent__execute`
- `select_fields`
- `execution_metadata.execution_time_ms`
- `wall_clock_ms` copied from execution metadata

## Export Gates

Markdown and chart exports are blocked when:

- required replay recordings are missing,
- Agent MCP recordings are stale or missing `select_fields`,
- any benchmark cell errors or is skipped.

## Why Token Reduction Matters

Reducing the token count of tool responses affects LLM-based agents in three dimensions:

- **Latency.** LLM inference time scales with input token count. A tool response with 200 tokens is processed significantly faster than one with 15,000 tokens. In agentic workflows where multiple tool calls happen sequentially, these savings compound across each step.
- **Cost.** LLM APIs charge per token for both input and output. Every token in a tool response is an input token the LLM must consume on the next turn. Reducing response payload sizes directly reduces the per-call cost of agentic workflows.
- **Context window pressure.** LLMs have finite context windows. Large tool responses consume a disproportionate share of available context, leaving less room for conversation history, system instructions, and subsequent tool calls. As the context fills, the model's ability to reason accurately degrades — an effect sometimes called "lost in the middle." Compact responses preserve context budget for what matters.

The benchmark quantifies these differences by measuring raw token counts on identical data operations across paths.

