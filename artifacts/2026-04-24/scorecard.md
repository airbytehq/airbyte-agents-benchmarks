# Agent Engine Launch Benchmark - April 22, 2026

**Date:** 2026-04-24  
**Paths compared:** Agent Engine SDK vs Agent Engine MCP vs Claude cloud MCP  
**Connectors:** granola, linear  
**Cells included:** 18/27

**Status:** Interim scorecard. Slack is pending a fresh successful run before this becomes the final 27-cell launch scorecard.

**Interim TL;DR.** Across the three benchmark tasks on each included connector, Agent Engine with `select_fields` returns roughly **12.7× fewer tokens** than the full SDK payload and ships the same structured records. It also uses **2.6× fewer tokens** than Claude cloud MCPs on the included cells. Compared to Claude cloud MCPs, Agent Engine matches or beats on record count, single-record-fetch cost, and bulk-list capability - and crucially preserves typed JSON (vs Claude MCP's mixed JSON, text, and markdown-like shapes) so agents can filter, sort, and join programmatically.

## Methodology

Three paths race the same three tasks on each connector:

| Path | Transport | Timing |
|---|---|---|
| **Agent Engine SDK** | `airbyte-agent-sdk` Python package → Agent Engine API | Client wall-clock |
| **Agent Engine MCP** | Hosted MCP proxy (`mcp.airbyte.ai`) → Agent Engine API | `execution_metadata.execution_time_ms` from the MCP response |
| **Claude cloud MCP** | Anthropic-hosted MCP (`mcp__claude_ai_*`) → vendor API | **Not captured.** Claude Code tool-call latency is not accessible from the harness; latency reported as 0 and should be read as "unmeasured in this run" (see March 3 scorecard for timed reference) |

Metrics:
- **Records** — count in the response
- **Tokens** — cl100k (tiktoken) on the raw response payload the agent consumes
- **Bytes** — UTF-8 length of JSON-encoded response
- **API calls** — tool invocations per task. In the included Linear list task, Claude returns 25 records while Agent Engine returns 50 records in one call.
- **Single-record-fetch cost** — tokens + calls to retrieve one record by ID (task 2 only)

Notes:
- Agent Engine MCP and SDK are both read-throughs of the same Agent Engine API — the MCP adds HTTP proxy overhead. `execution_time_ms` from the MCP response reflects Agent Engine server-side processing; client-side wall-clock (SDK path) includes both network round-trips and SDK deserialization.
- Claude cloud MCP connectors return varying shapes: Slack returns markdown-like text, Linear returns structured JSON, Granola returns an aggregated string for list_meetings and a natural-language synthesis for query_granola_meetings.

## Granola

| Task | Path | Records | Tokens | Bytes | Calls | Latency (ms) |
|---|---|---:|---:|---:|---:|---:|
| Search notes by keyword | Agent Engine SDK | 1 | 11,487 | 31,217 | 1 | 1125 |
|  | Agent Engine MCP | 1 | 234 | 1,010 | 1 | 1097 |
|  | Claude cloud MCP | 1 | 92 | 399 | 1 | 0 |
| Get single note by ID (with transcript) | Agent Engine SDK | 1 | 944 | 4,132 | 1 | 1174 |
|  | Agent Engine MCP | 1 | 127 | 468 | 1 | 1536 |
|  | Claude cloud MCP | 1 | 3,224 | 14,090 | 1 | 0 |
| List first 25 notes | Agent Engine SDK | 25 | 2,443 | 5,964 | 1 | 1278 |
|  | Agent Engine MCP | 25 | 1,124 | 2,559 | 1 | 1169 |
|  | Claude cloud MCP | 1 | 1,802 | 5,705 | 1 | 0 |

**Takeaway:** Agent Engine MCP consumes the fewest tokens (**1,485** vs Agent Engine SDK's **14,874** — **10.0× fewer**).

## Linear

| Task | Path | Records | Tokens | Bytes | Calls | Latency (ms) |
|---|---|---:|---:|---:|---:|---:|
| Search issues by keyword | Agent Engine SDK | 10 | 37,145 | 67,761 | 1 | 2201 |
|  | Agent Engine MCP | 10 | 1,225 | 3,180 | 1 | 2121 |
|  | Claude cloud MCP | 10 | 4,828 | 15,096 | 1 | 0 |
| Get single issue by ID | Agent Engine SDK | 1 | 458 | 1,652 | 1 | 1407 |
|  | Agent Engine MCP | 1 | 175 | 439 | 1 | 2184 |
|  | Claude cloud MCP | 1 | 610 | 2,208 | 1 | 0 |
| List first 50 issues | Agent Engine SDK | 50 | 14,110 | 38,108 | 1 | 1339 |
|  | Agent Engine MCP | 50 | 2,344 | 6,923 | 1 | 1153 |
|  | Claude cloud MCP | 25 | 3,072 | 8,558 | 1 | 0 |

**Takeaway:** Agent Engine MCP consumes the fewest tokens (**3,744** vs Agent Engine SDK's **51,713** — **13.8× fewer**).

## Aggregate

| Path | Tasks OK | Tokens (sum) | Bytes (sum) | Calls (sum) | Latency ms (sum) |
|---|---:|---:|---:|---:|---:|
| Agent Engine SDK | 6 | 66,587 | 148,834 | 6 | 8,524 |
| Agent Engine MCP | 6 | 5,229 | 14,579 | 6 | 9,260 |
| Claude cloud MCP | 6 | 13,628 | 46,056 | 6 | 0 |

## Verdict

- **Agent Engine MCP** (with `select_fields`) is the narrowest path — 12.7× fewer tokens than the full SDK, 2.6× fewer than Claude cloud MCP.
- **Agent Engine SDK** returns full typed records — useful when agents need all fields, e.g. for multi-field joins.
- **Claude cloud MCP** is structurally narrower in some cases, but gives up queryability (structured filters) and returns inconsistent shapes across connectors (JSON, text, and markdown-like responses). In the included Linear list task, Claude returns 25 records while Agent Engine returns 50 records in one call.

**For marketing:** Agent Engine MCP + SDK deliver narrower, structured, queryable data in one call. Claude cloud MCP requires pagination, returns mixed shapes, and lacks filter operators.
