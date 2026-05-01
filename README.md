# Airbyte Agents Benchmarks

A head-to-head benchmark measuring the cost and capability of accessing business data through Airbyte's Agent MCP versus vendor-provided native MCP servers.

## Why Agent MCP

| | Native MCP (per vendor) | Airbyte Agent MCP |
|---|---|---|
| **Setup** | Per-vendor server install; some require admin privileges (e.g., Salesforce Connected App) | One hosted endpoint — no per-vendor setup |
| **Credentials** | One secret per vendor (5 vendors = 5 credential sets) | One Airbyte credential for all connectors |
| **Token efficiency** | Full API objects (30-200+ fields per record) | Only requested fields (`select_fields`) — **74% fewer tokens** |
| **Capability** | Limited to vendor's tool set; missing ops require workarounds | Context store provides get, list, and search for every entity |

Across five connectors (Gong, Linear, Salesforce, Slack, Zendesk) and 14 comparable scenarios, Agent MCP used **74% fewer tokens** than native MCP servers for the same data operations:

| Connector | Agent MCP tokens | Native MCP tokens | Savings |
|---|---:|---:|---:|
| Gong | 6,234 | 52,946 | 88% |
| Zendesk | 4,161 | 26,173 | 84% |
| Linear | 9,606 | 18,758 | 49% |
| Slack | 6,985 | 13,416 | 48% |
| Salesforce | 2,742 | 4,610 | 41% |

For the full benefits narrative — including setup complexity, credential management, capability gaps, and cross-connector workflow results — see **[docs/BENEFITS.md](docs/BENEFITS.md)**.

## Benchmark Design

The harness compares three paths for the same tasks:

| Path | Slug | Description |
|---|---|---|
| REST Baseline (via SDK) | `agent-sdk` | Token cost of consuming the provider's full REST API response. See [Methodology](docs/METHODOLOGY.md#agent-sdk-as-rest-baseline). |
| Agent MCP | `agent-mcp` | Record-replay of the hosted Airbyte Platform MCP with mandatory `select_fields` |
| Native MCP | `native-mcp` | Record-replay of vendor-native MCP server responses |

Each connector has named scenarios (e.g., `linear-search`, `gong-get`, `slack-list-all`). The benchmark currently covers five connectors. Granola recordings from April 24 are preserved but the connector is tombstoned.

## Quick Start (No Credentials)

The `native-mcp` replay path can be validated and run using only the committed recordings, with no API access or environment variables required.

```bash
git clone https://github.com/airbytehq/airbyte-agents-benchmarks.git
cd airbyte-agents-benchmarks
uv sync
uv run pytest -q
uv run agent-bench run \
  --scenarios linear,slack,gong,salesforce,zendesk \
  --paths agent-mcp \
  --export-markdown results.md
```

> **Note:** Validating `agent-mcp` recordings requires env vars because the validator checks `connector_id` consistency with your configured environment. If you only want to inspect the replay data without credentials, validate the `native-mcp` path alone or read the recordings directly.

See [docs/REPRODUCTION.md](docs/REPRODUCTION.md) for the full reproduction guide, including live SDK setup, credential acquisition, and troubleshooting.

## Connectors

| Connector | Agent MCP | Native MCP |
|---|---|---|
| Linear | ✅ | [Linear MCP](https://linear.app/docs/mcp) |
| Slack | ✅ | [`@modelcontextprotocol/server-slack`](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack) |
| Gong | ✅ | [`kenazk/gong-mcp`](https://github.com/kenazk/gong-mcp) |
| Salesforce | ✅ | [`mcp-salesforce-connector`](https://github.com/smn2gnt/mcp-salesforce) |
| Zendesk | ✅ | [`dunialabs/mcp-zendesk`](https://github.com/dunialabs/mcp-servers/tree/main/mcp-zendesk) |

## Artifact Layout

Each benchmark run produces immutable artifacts under a dated directory:

```
artifacts/
  YYYY-MM-DD/
    linear-search-scenario/
      agent-mcp/
        recording.json
        recording-stats.json
      native-mcp/
        recording.json
        recording-stats.json
    gong-get-scenario/
      ...
    benchmark-result-report.md
    charts/
```

A symlink at `latest-benchmark-result-report.md` in the repo root points to the most recent report.

## CLI Reference

```text
agent-bench list       List available benchmark scenarios
agent-bench plan       Print MCP tool-call specs for record-replay paths
agent-bench run        Run the benchmark across selected scenarios and paths
agent-bench validate   Validate replay recordings before exporting
```

All commands accept `--scenarios` and `--paths` filters. Pass connector names (e.g. `linear`) to `--scenarios` to select all scenarios for that connector, or pass specific scenario names (e.g. `linear-search,linear-get`). Use `--help` on any command for full options.

Export is blocked when recordings or cells have issues. See [docs/METHODOLOGY.md](docs/METHODOLOGY.md#export-gates) for the full list of export gates.

## Recording New Responses

```bash
uv run agent-bench plan --scenarios all --paths native-mcp,agent-mcp
```

For each Agent MCP connector, call `mcp__airbyte-agent__describe_connector` once before recording the planned `mcp__airbyte-agent__execute` call. Every execute item must include `select_fields`.

Save MCP responses with:

```bash
uv run python scripts/record_response.py \
  --path agent-mcp \
  --scenario linear-search \
  --tool mcp__airbyte-agent__execute \
  --args '{"items":[...]}' \
  --response-file /tmp/response.json \
  --reset
```

For Agent MCP, `--wall-ms` can be omitted when the response contains `execution_metadata.execution_time_ms`.

## Further Reading

- [Benefits Deep-Dive](docs/BENEFITS.md) — setup, credentials, token efficiency, and capability comparison
- [Methodology](docs/METHODOLOGY.md) — measurement design, token counting, timing
- [Reproduction Guide](docs/REPRODUCTION.md) — end-to-end walkthrough from clone to results
- [Third-Party MCP Setup](docs/THIRD_PARTY_MCP_SETUP.md) — install and configure vendor MCP servers
