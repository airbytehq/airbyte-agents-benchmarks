# Airbyte Agents Benchmarks

A head-to-head benchmark measuring the cost and capability of accessing business data through Airbyte's Agent MCP versus vendor-provided native MCP servers.

## Why Agent MCP

| | Native MCP (per vendor) | Airbyte Agent MCP |
|---|---|---|
| **Setup** | Per-vendor server install; some require admin privileges (e.g., Salesforce Connected App) | One hosted endpoint — no per-vendor setup |
| **Credentials** | One secret per vendor (5 vendors = 5 credential sets) | One Airbyte credential for all connectors |
| **Token efficiency** | Full API objects (30-200+ fields per record) | Only requested fields (`select_fields`) — significantly fewer tokens |
| **Capability** | Limited to vendor's tool set; missing ops require workarounds | Context store provides get, list, and search for every entity |

Across five connectors (Gong, Linear, Salesforce, Slack, Zendesk), Agent MCP uses significantly fewer tokens than native MCP servers for comparable data operations. See the **[latest comparison report](latest_comparison_report/)** for current per-connector numbers.

For the full benefits narrative — including setup complexity, credential management, capability gaps, and cross-connector workflow results — see **[docs/BENEFITS.md](docs/BENEFITS.md)**.

## Benchmark Design

The harness compares three paths for the same tasks:

| Path | Slug | Description |
|---|---|---|
| REST Baseline (via SDK) | `agent-sdk` | Token cost of consuming the provider's full REST API response. See [Methodology](docs/METHODOLOGY.md#agent-sdk-as-rest-baseline). |
| Agent MCP | `agent-mcp` | Record-replay of the hosted Airbyte Platform MCP with mandatory `select_fields` |
| Native MCP | `native-mcp` | Record-replay of vendor-native MCP server responses |

Each connector has named scenarios (e.g., `linear-search`, `gong-get`, `slack-list-all`). The benchmark currently covers five connectors. Granola recordings from April 24 are preserved but the connector is tombstoned.

## Connectors

| Connector | Agent MCP | Native MCP |
|---|---|---|
| Linear | ✅ | [Linear MCP](https://linear.app/docs/mcp) |
| Slack | ✅ | [`@modelcontextprotocol/server-slack`](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack) |
| Gong | ✅ | [`kenazk/gong-mcp`](https://github.com/kenazk/gong-mcp) |
| Salesforce | ✅ | [`mcp-salesforce-connector`](https://github.com/smn2gnt/mcp-salesforce) |
| Zendesk | ✅ | [`dunialabs/mcp-zendesk`](https://github.com/dunialabs/mcp-servers/tree/main/mcp-zendesk) |

## Further Reading

- [Benefits Deep-Dive](docs/BENEFITS.md) — setup, credentials, token efficiency, and capability comparison
- [Methodology](docs/METHODOLOGY.md) — measurement design, token counting, timing
- [Reproduction Guide](docs/REPRODUCTION.md) — end-to-end walkthrough from clone to results
- [Third-Party MCP Setup](docs/THIRD_PARTY_MCP_SETUP.md) — install and configure vendor MCP servers
