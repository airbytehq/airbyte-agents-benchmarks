# CTO Brief

## What This Repo Contains

This is a private handoff package for the Airbyte Agents launch benchmark. It includes:

- the runnable Python benchmark harness,
- Linear and Granola replay recordings,
- the April 24, 2026 interim scorecard,
- generated charts,
- a supporting image-only deck artifact.

The harness is the source of truth. The deck is included for context only and should not be treated as editable benchmark source.

## Current Result

Across Linear and Granola, Agent MCP with `select_fields` used:

- `5,229` tokens total,
- `12.7x` fewer tokens than the REST Baseline path (`66,587` tokens),
- `2.6x` fewer tokens than native vendor MCPs (`13,628` tokens).

**Important caveat:** The REST Baseline-vs-MCP token ratio primarily reflects field projection (`select_fields` narrows to 6-10 fields vs the REST Baseline's full 30-50+ fields), not transport or protocol differences. The MCP-vs-native ratio is also affected by non-equivalent task semantics in some cells (see Known Issues).

The current result includes 18 of 27 planned cells. Slack is intentionally excluded from the scorecard until search readiness and replay recordings are complete.

The April 24 scorecard is the frozen launch artifact for these headline numbers. The REST Baseline path runs live and can drift as connector data changes; an April 27 verification run completed but produced a lower live Baseline total (`53,000` tokens). The replay totals for Agent MCP and Native MCP remained unchanged.

## Why This Matters

The benchmark demonstrates that Airbyte Agents can give agents structured, queryable data without forcing them to ingest full records.

The important distinction is not simply "shorter output." The stronger claim is:

- Agent MCP narrows payloads with explicit field selection.
- The REST Baseline (via SDK) shows the token cost of consuming the provider's full REST API response — useful when agents need complete records.
- Both paths preserve typed records for filtering, sorting, joins, and follow-up actions.

Native MCP responses are useful but inconsistent across connectors. In this result set, they include mixed JSON, text, and markdown-like shapes. That makes programmatic downstream work harder to generalize.

## Safe External Claims

Safe:

- "Agent MCP with `select_fields` returns narrower payloads than the full REST Baseline response."
- "Selecting 6-10 fields instead of 30-50+ fields reduces token count by approximately 10-13x."
- "Agent MCP preserves typed JSON while narrowing payload fields, enabling downstream programmatic filtering and joins."
- "In the included Linear list task, Airbyte Agents returns 50 records in one call while native MCP returns 25 records."

Avoid:

- Claiming the REST Baseline-vs-MCP ratio reflects protocol efficiency (it primarily reflects field projection).
- "Final 27-cell result" until Slack is complete.
- "Slack search works" while Context Store search still returns HTTP 503.
- "Native MCP is always markdown/prose" because output shapes are mixed.
- "Native MCP latency is zero" because this harness does not capture native MCP latency.
- Any aggregate ratio that includes the Granola native-MCP search cell (empty-state response) or the Granola get task (non-equivalent transcript semantics).

## What Must Happen Before Final Launch Use

1. Replace synthetic Linear list recording (`issue-00` through `issue-49`) with real API output.
2. Fix Granola get task: either add `transcript` to Agent MCP `select_fields` and re-record, or re-record native MCP without transcript.
3. Replace Granola native-MCP search recording (currently an empty-state response, not a real search result).
4. Add an "SDK with projection" path to isolate the field-projection effect from protocol differences.
5. Slack Context Store search must stop returning HTTP 503.
6. Slack `agent-mcp` and `native-mcp` recordings must be captured for search, get, and list.
7. `uv run agent-bench validate --scenarios all --paths native-mcp,agent-mcp` must pass.
8. Full export must run with `--scenarios all --paths all`.
9. Final scorecard and charts should be reviewed for any connector-specific caveats before publication.
