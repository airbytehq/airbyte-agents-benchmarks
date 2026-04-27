# CTO Brief

## What This Repo Contains

This is a private handoff package for the Agent Engine launch benchmark. It includes:

- the runnable Python benchmark harness,
- Linear and Granola replay recordings,
- the April 24, 2026 interim scorecard,
- generated charts,
- a supporting image-only deck artifact.

The harness is the source of truth. The deck is included for context only and should not be treated as editable benchmark source.

## Current Result

Across Linear and Granola, Agent Engine MCP with `select_fields` used:

- `5,229` tokens total,
- `12.7x` fewer tokens than the SDK/API path (`66,587` tokens),
- `2.6x` fewer tokens than Claude cloud MCP (`13,628` tokens).

The current result includes 18 of 27 planned cells. Slack is intentionally excluded from the scorecard until search readiness and replay recordings are complete.

The April 24 scorecard is the frozen launch artifact for these headline numbers. The SDK/API path runs live and can drift as connector data changes; an April 27 verification run completed but produced a lower live SDK/API total (`53,000` tokens). The replay totals for Agent Engine MCP and Claude MCP remained unchanged.

## Why This Matters

The benchmark demonstrates that Agent Engine can give agents structured, queryable data without forcing them to ingest full records.

The important distinction is not simply "shorter output." The stronger claim is:

- Agent Engine MCP narrows payloads with explicit field selection.
- Agent Engine SDK/API remains available when an agent needs complete records.
- Both Agent Engine paths preserve typed records for filtering, sorting, joins, and follow-up actions.

Claude cloud MCP responses are useful but inconsistent across connectors. In this result set, they include mixed JSON, text, and markdown-like shapes. That makes programmatic downstream work harder to generalize.

## Safe External Claims

Safe:

- "In the current Linear+Granola benchmark, Agent Engine MCP used 12.7x fewer tokens than the SDK/API path."
- "Agent Engine MCP used 2.6x fewer tokens than Claude cloud MCP on the included cells."
- "Agent Engine MCP preserves typed JSON while narrowing payload fields."
- "Linear's roughly 14x token reduction is an overall connector-level result across search, get, and list."
- "In the included Linear list task, Agent Engine returns 50 records in one call while Claude cloud MCP returns 25 records."

Avoid:

- "Final 27-cell result" until Slack is complete.
- "Slack search works" while Context Store search still returns HTTP 503.
- "Claude MCP is always markdown/prose" because output shapes are mixed.
- "Claude latency is zero" because this harness does not capture Claude cloud MCP latency.

## What Must Happen Before Final Launch Use

1. Slack Context Store search must stop returning HTTP 503.
2. Slack `ae-mcp` and `claude` recordings must be captured for search, get, and list.
3. `uv run agent-bench validate --connectors all --paths claude,ae-mcp` must pass.
4. Full export must run with `--connectors all --paths all`.
5. Final scorecard and charts should be reviewed for any connector-specific caveats before publication.
