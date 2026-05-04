# Airbyte Agents Benchmarks

A head-to-head benchmark comparing Airbyte's Agent MCP with vendor-provided native MCP servers, focusing on measuring the cost and capability of accessing business data in common use cases.

## Benchmark Design

The harness compares token usage for tool calls of the the same tasks performed on the Agent MCP, compared with the native or third party MCP Servers dedicated to these applications.

> [!Note]
> For consistency and repeatability, the benchmark results do not test the LLM itself - only the tool calls themselves are evaluated.

## MCP Servers Tested

| Connector | Agent MCP | Native MCP |
|---|---|---|
| Linear | ✅ | [Linear MCP](https://linear.app/docs/mcp) |
| Slack | ✅ | [Slack Hosted MCP](https://docs.slack.dev/ai/slack-mcp-server) |
| Gong | ✅ | [`kenazk/gong-mcp`](https://github.com/kenazk/gong-mcp) |
| Salesforce | ✅ | [`mcp-salesforce-connector`](https://github.com/smn2gnt/mcp-salesforce) |
| Zendesk | ✅ | [`dunialabs/mcp-zendesk`](https://github.com/dunialabs/mcp-servers/tree/main/mcp-zendesk) |

## Why Airbyte Agent MCP

| | Native MCP (per vendor) | Airbyte Agent MCP |
|---|---|---|
| **Setup** | Per-vendor server install; some require admin privileges (e.g., Salesforce Connected App) | One hosted endpoint — no per-vendor setup |
| **Credentials** | One secret per vendor (5 vendors = 5 credential sets) | One Airbyte credential for all connectors |
| **Token efficiency** | Full API objects (30-200+ fields per record) | Only requested fields (`select_fields`) — significantly fewer tokens |
| **Capability** | Limited to vendor's tool set; missing ops require workarounds | Context store provides get, list, and search for every entity |

Across four out of five connectors (Gong, Linear, Slack, Zendesk) analyzed, Agent MCP uses significantly fewer tokens than native MCP servers for comparable data operations. Only the Salesforce MCP has similar token usage, due to built-in field and record capabilities of the SOQL query interface. However, Salesforce MCP requires admin support and elevated permissions upon Salesforce itself.

See the **[latest comparison report](latest_comparison_report/)** for current per-connector numbers.

For a more complete comparison of benefits — including setup complexity, credential management, and capability gaps — see **[docs/BENEFITS.md](docs/BENEFITS.md)**.

## Further Reading

- [Benefits Deep-Dive](docs/BENEFITS.md) — setup, credentials, token efficiency, and capability comparison
- [Methodology](docs/METHODOLOGY.md) — measurement design, token counting, timing
- [Reproduction Guide](docs/REPRODUCTION.md) — end-to-end walkthrough from clone to results
- [Third-Party MCP Setup](docs/THIRD_PARTY_MCP_SETUP.md) — install and configure vendor MCP servers
