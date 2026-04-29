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
| REST Baseline (via SDK) | 6 | 66,587 |
| Agent MCP | 6 | 5,229 |
| Native MCP | 6 | 13,628 |

Headline ratios:

- Agent MCP used `12.7x` fewer tokens than the REST Baseline path. **Caveat:** this ratio primarily reflects field projection (`select_fields` narrows to 6-10 fields vs the REST Baseline's full record), not transport or protocol differences.
- Agent MCP used `2.6x` fewer tokens than native vendor MCPs. **Caveat:** some cells are not semantically equivalent (see Known Issues below).

## Connector-Level Results

| Connector | REST Baseline tokens | Agent MCP tokens | Native MCP tokens | MCP vs Baseline |
|---|---:|---:|---:|---:|
| Granola | 14,874 | 1,485 | 5,118 | 10.0x fewer |
| Linear | 51,713 | 3,744 | 8,510 | 13.8x fewer |

Important caveat for deck/chart language: Linear's roughly `14x` claim is the overall Linear connector result across search, get, and list. It is not a list-only claim.

## Safe Claims

Safe to say:

- Agent MCP with `select_fields` returns narrower payloads than the full REST Baseline response. In the current benchmark, selecting 6-10 fields instead of 30-50+ fields reduces token count significantly.
- Field projection (`select_fields`) is the primary driver of token reduction between Agent MCP and the REST Baseline.
- Agent MCP preserves typed JSON while narrowing payload shape, enabling downstream programmatic filtering and joins.
- Native MCP output shapes vary by connector. In the included cells, they are mixed JSON, text, and markdown-like responses.
- In the included Linear list task, Airbyte Agents returns 50 records in one call while native MCP returns 25 records.

Do not claim yet:

- That the REST Baseline-vs-MCP token ratio reflects protocol efficiency (it primarily reflects field projection).
- That the benchmark is final across all Slack, Linear, and Granola cells.
- That Slack search is healthy.
- That native MCP latency is measured by this harness.
- That native MCP outputs are always markdown or prose.
- That "50 records in one call" applies to every connector in the benchmark.

## Known Issues

The following issues affect the current result set and should be resolved before external publication:

1. **Linear list recording is synthetic.** The Agent MCP Linear list recording uses placeholder IDs (`issue-00` through `issue-49`) with hourly timestamps and missing fields. Real API data would produce higher token counts.
2. **Granola get task is not semantically equivalent.** The native MCP path fetches the full meeting transcript; the Agent MCP path returns `transcript: null`. This inflates the native MCP token count relative to Agent MCP for this task.
3. **Granola native-MCP search is an empty-state response.** The recording is a conversational "I don't have any data" message, not a real search result.
4. **Linear search results contain stringified objects.** The `state`, `team`, and `labels` fields are serialized as `"{}"` strings instead of proper objects, suggesting a context store serialization issue.

## Reproduction

See [REPRODUCTION.md](REPRODUCTION.md) for the full step-by-step walkthrough, from clone to validated results.

The committed April 24 scorecard is the frozen artifact for the headline `66,587` REST Baseline token total. The REST Baseline path is live, so re-running the command can produce a different total when connector data changes. The replay paths are deterministic from `assets/recordings/`.

On April 27, 2026, a live Linear+Granola verification run completed successfully with replay totals unchanged (`5,229` Agent MCP tokens and `13,628` Native MCP tokens), while the live REST Baseline total was `53,000` tokens.
