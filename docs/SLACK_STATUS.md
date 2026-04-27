# Slack Status

## Current State

Slack is not included in the April 24, 2026 scorecard because the full Slack path is not ready.

Current local connector ID verified on April 27, 2026:

```text
08b41f8a-f0b9-41e4-8406-bb11246e410c
```

Observed live behavior:

- `get` and `list` can pass through the Agent Engine SDK path.
- `search` may return HTTP 503 while Context Store preview builds.
- The 503 is a readiness blocker, not currently treated as a harness bug.

The scenario target used by the harness is:

- Slack channel ID: `C02TD5CB7PZ`
- Name hint: `feedback_survey_results`

## Smoke Test

Use this command to verify the live SDK path:

```bash
uv run agent-bench run --connectors slack --paths ae-sdk
```

Current expected state:

- `get`: pass
- `list`: pass
- `search`: may fail with HTTP 503

## Steps To Finish Slack

1. Re-run the Slack SDK smoke test and confirm search no longer returns HTTP 503.
2. Capture fresh Agent Engine MCP recordings for Slack search, get, and list.
3. Capture fresh Claude cloud MCP recordings for Slack search, get, and list.
4. Validate all replay paths:

```bash
uv run agent-bench validate --connectors all --paths claude,ae-mcp
```

5. Run the full 27-cell export:

```bash
uv run agent-bench run \
  --connectors all \
  --paths all \
  --export-markdown artifacts/2026-04-24/final-scorecard.md \
  --export-charts artifacts/2026-04-24/final-charts
```

Do not publish the full scorecard until this command completes without skipped or failed cells.
