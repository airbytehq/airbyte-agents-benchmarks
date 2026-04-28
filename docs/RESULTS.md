# Results

## Current Status

The included launch artifact is an interim scorecard dated April 24, 2026.

| Scope | Status |
|---|---|
| Linear | Reproducible |
| Granola | Reproducible |
| Slack | Blocked on search readiness and replay recordings |
| Cells included | 18 of 27 |

Primary artifact:

- `artifacts/2026-04-24/scorecard.md`
- `artifacts/2026-04-24/charts/`
- `artifacts/2026-04-24/deck/agent-engine-benchmark-deck-image-only.pptx`

The deck is included only as a supporting, image-only/non-editable artifact. The runnable harness and exported scorecard are the source of truth.

## Aggregate Token Results

Linear + Granola, all three tasks, all three paths:

| Path | Tasks OK | Tokens |
|---|---:|---:|
| Agent Engine SDK/API | 6 | 66,587 |
| Agent Engine MCP | 6 | 5,229 |
| Claude cloud MCP | 6 | 13,628 |

Headline ratios:

- Agent Engine MCP used `12.7x` fewer tokens than the SDK/API path.
- Agent Engine MCP used `2.6x` fewer tokens than Claude cloud MCP.

## Connector-Level Results

| Connector | Agent Engine SDK/API tokens | Agent Engine MCP tokens | Claude cloud MCP tokens | MCP vs SDK/API |
|---|---:|---:|---:|---:|
| Granola | 14,874 | 1,485 | 5,118 | 10.0x fewer |
| Linear | 51,713 | 3,744 | 8,510 | 13.8x fewer |

Important caveat for deck/chart language: Linear's roughly `14x` claim is the overall Linear connector result across search, get, and list. It is not a list-only claim.

## Safe Claims

Safe to say:

- Agent Engine MCP with `select_fields` is the narrowest measured path in the current 18-cell result set.
- Agent Engine SDK/API returns full typed records, useful when an agent needs all fields.
- Agent Engine MCP preserves typed JSON while narrowing payload shape.
- Claude cloud MCP output shapes vary by connector. In the included cells, they are mixed JSON, text, and markdown-like responses.
- In the included Linear list task, Agent Engine returns 50 records in one call while Claude cloud MCP returns 25 records.

Do not claim yet:

- That the benchmark is final across all Slack, Linear, and Granola cells.
- That Slack search is healthy.
- That Claude MCP latency is measured by this harness.
- That Claude MCP outputs are always markdown or prose.
- That "50 records in one call" applies to every connector in the benchmark.

## Reproduction

See [REPRODUCTION.md](REPRODUCTION.md) for the full step-by-step walkthrough, from clone to validated results.

The committed April 24 scorecard is the frozen artifact for the headline `66,587` SDK/API token total. The SDK/API path is live, so re-running the command can produce a different SDK/API total when connector data changes. The replay paths are deterministic from `assets/recordings/`.

On April 27, 2026, a live Linear+Granola verification run completed successfully with replay totals unchanged (`5,229` Agent Engine MCP tokens and `13,628` Claude MCP tokens), while the live SDK/API total was `53,000` tokens.
