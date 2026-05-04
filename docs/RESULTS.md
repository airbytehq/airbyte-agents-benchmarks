# Results

The latest benchmark results are in the auto-generated comparison report:

- **[`latest_comparison_report/`](../latest_comparison_report/)** — current report with per-connector and per-scenario breakdowns

The report is regenerated each time the harness runs with `--export-markdown`. Dated artifacts are preserved under `artifacts/YYYY-MM-DD/`.

## Interpreting the Report

- **Agent MCP** token counts reflect responses after `select_fields` narrows the returned fields (typically 4-9 fields per record).
- **Native MCP** token counts reflect the vendor MCP server's full response, which varies in shape across connectors (structured JSON, text, or markdown-like).
- **Ratio** is Agent MCP tokens as a percentage of Native MCP tokens. Lower is better.
- **Savings** is `100% - Ratio`.

Token ratios between Agent MCP and Native MCP primarily reflect the effect of field selection — Agent MCP's `select_fields` narrows responses to 4-9 fields versus 30-200+ from native servers. See [METHODOLOGY.md](METHODOLOGY.md#token-counting) for details.

## Known Caveats

The following caveats apply to the current result set:

1. **Native MCP recordings are not available for all connectors.** The comparison report only includes connectors that have both Agent MCP and Native MCP recordings. See the [README](../README.md#connectors) for the current coverage matrix.

2. **Multi-step scenarios measure data-path tokens only, not end-to-end agent cost.** Cross-connector workflows like `gong-to-salesforce-zendesk-lookup` use statically seeded inputs for downstream steps (identical seeds across both paths). This means the benchmark does *not* count the LLM tokens that a real agent loop would spend on chain reasoning — extracting account names from Step 1, normalizing them, and formatting them into Step 2. Those costs scale with Step 1's response size, so the real-world delta in favor of smaller payloads is likely larger than what these numbers show. See [METHODOLOGY.md → Multi-Step Scenarios](METHODOLOGY.md#multi-step-scenarios) for the full disclosure.

For claims guidance and a narrative summary of the benchmark findings, see [BENEFITS.md](BENEFITS.md).

## Reproduction

See [REPRODUCTION.md](REPRODUCTION.md) for the full step-by-step walkthrough, from clone to validated results.
