# Token Efficiency Comparison Report

**Date:** 2026-04-30  
**Compared paths:** Agent MCP vs Native MCP  
**Connectors:** Gong, Linear, Multi_Source, Salesforce, Slack, Zendesk

## Per-Scenario Breakdown

### Gong

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Look up a single Gong call by ID.<br>Agent requests id, title, scheduled, and duration. | 💎Only requested fields consume token context: `id`, `title`, `scheduled`, and `duration`. |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 195 | 279 | 1 | 1 | 70% | 30% | 💎Only requested fields consume token context: `id`, `title`, `scheduled`, and `duration`. |

**Connector total:** Agent MCP uses 70% of Native MCP tokens (30% savings)

#### Benchmarks Not Comparable

These scenarios could not produce a valid comparison between Agent MCP and the vendor's native MCP server.

| Action | Description | Annotations |
|---|---|---|
| search | Search Gong calls matching a keyword.<br>Agent requests id, title, scheduled, and duration per result. | ℹ️ The Gong REST API (and the third-party kenazk/gong-mcp server) does not expose a keyword/text search endpoint. Native MCP can only list calls by date range with a fixed page size of 100. Agent-mcp uses context_store_search with fuzzy matching, a capability that has no native equivalent. |

**Scenario definitions:** [gong-get](../../src/agent_bench/scenarios/gong-get.yaml) | [gong-search](../../src/agent_bench/scenarios/gong-search.yaml)

### Linear

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Look up a single Linear issue by ID.<br>Agent requests id, identifier, title, state, priority, createdAt, updatedAt, team, and labels. | ℹ️ The agent-mcp connector and native Linear MCP are currently connected to different Linear workspaces. Agent-mcp syncs from the AGENTIC workspace (issues prefixed `AGENTIC-`), while the native MCP API key connects to `airbyte-integration-testing` (issues prefixed `AIR-`). Each path fetches a valid single issue from its own workspace; the benchmark measures token overhead, not data identity. |
| search | Search Linear issues by keyword.<br>Agent requests id, identifier, title, state, priority, createdAt, updatedAt, team, and labels per result. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 263 | 311 | 1 | 1 | 85% | 15% | ℹ️ The agent-mcp connector and native Linear MCP are currently connected to different Linear workspaces. Agent-mcp syncs from the AGENTIC workspace (issues prefixed `AGENTIC-`), while the native MCP API key connects to `airbyte-integration-testing` (issues prefixed `AIR-`). Each path fetches a valid single issue from its own workspace; the benchmark measures token overhead, not data identity. |
| search | 944 | 1,044 | 7 | 3 | 90% | 10% |  |

**Connector total:** Agent MCP uses 89% of Native MCP tokens (11% savings)

**Scenario definitions:** [linear-get](../../src/agent_bench/scenarios/linear-get.yaml) | [linear-search](../../src/agent_bench/scenarios/linear-search.yaml)

### Multi_Source

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| multi-step | Multi-step cross-connector workflow: search for Gong calls scheduled<br>on 2026-04-28, then look up the associated account names in Salesforce and<br>find open tickets for those accounts in Zendesk.<br>Steps 2 and 3 use dummy static account/ticket lists to demonstrate<br>the choreographed multi-step scenario format. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| multi-step | 1,482 | 30,208 | 22 | 145 | 5% | 95% |  |

**Connector total:** Agent MCP uses 5% of Native MCP tokens (95% savings)

<details><summary>Per-tool-call breakdown: Cross-system: Gong calls on 2026-04-28 → Salesforce + Zendesk lookup</summary>

**Agent MCP** (3 calls)

| Step | Server | Tool | Tokens | Records |
|---:|---|---|---:|---:|
| 1 | airbyte-agent | integrations_connectors_id_execute | 1,143 | 20 |
| 2 | airbyte-agent | integrations_connectors_id_execute | 210 | 2 |
| 3 | airbyte-agent | integrations_connectors_id_execute | 129 | 0 |

**Native MCP** (3 calls)

| Step | Server | Tool | Tokens | Records |
|---:|---|---|---:|---:|
| 1 | gong | list_calls | 26,084 | 100 |
| 2 | salesforce | soqlQuery | 3,091 | 43 |
| 3 | zendesk | zendeskSearchTickets | 1,033 | 2 |

</details>

**Scenario definitions:** [gong-to-salesforce-zendesk-lookup](../../src/agent_bench/scenarios/gong-to-salesforce-zendesk-lookup.yaml)

### Salesforce

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Look up a single Salesforce account by ID.<br>Agent requests Id, Name, Type, and Industry. |  |
| search | Search Salesforce accounts matching a keyword.<br>Agent requests Id, Name, Type, and Industry per result. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 178 | 90 | 1 | 1 | 198% | -98% |  |
| search | 506 | 729 | 10 | 10 | 69% | 31% |  |

**Connector total:** Agent MCP uses 84% of Native MCP tokens (16% savings)

**Scenario definitions:** [salesforce-get](../../src/agent_bench/scenarios/salesforce-get.yaml) | [salesforce-search](../../src/agent_bench/scenarios/salesforce-search.yaml)

### Slack

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| list-all | List all non-archived Slack channels in the workspace (approximately 1,085 channels).<br>This represents a realistic "give me everything" use case.<br>Agent requests id, name, num_members, is_archived, is_private, created, updated, topic, and purpose per record.<br>Both paths exclude archived channels (agent-mcp via exclude_archived param,<br>native-mcp via @modelcontextprotocol/server-slack default behavior).<br>Agent-mcp paginates with limit=1000 per page (3 calls using next_cursor).<br>Native-mcp paginates with limit=100 per page (cursor-based, 21 calls).<br><br>Note: The YAML defines only the first page call. Subsequent pages are recorded<br>dynamically using the next_cursor returned in connector_metadata. The recording<br>script handles pagination automatically. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| list-all | 118,896 | 362,313 | 1085 | 1085 | 33% | 67% |  |

**Connector total:** Agent MCP uses 33% of Native MCP tokens (67% savings)

#### Benchmarks Not Comparable

These scenarios could not produce a valid comparison between Agent MCP and the vendor's native MCP server.

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Slack channel by ID.<br>Agent requests id, name, is_archived, is_private, created, updated, topic, and purpose. | ℹ️ The Slack connector's context store is not populated in the benchmark workspace. `context_store_search` with `eq: {id: "C02TD5CB7PZ"}` returns `data: []`. This scenario uses `action: get` as a direct lookup instead.; 🛑No native get-by-ID tool exists in [@modelcontextprotocol/server-slack](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack) ([v2025.4.25](https://www.npmjs.com/package/@modelcontextprotocol/server-slack)). All 8 tools: `slack_list_channels`, `slack_post_message`, `slack_reply_to_thread`, `slack_add_reaction`, `slack_get_channel_history`, `slack_get_thread_replies`, `slack_get_users`, `slack_get_user_profile`. None accept a channel ID and return a single channel. Alternative path: paginate `slack_list_channels` until the target channel is found (est. approximately 13,400 tokens to scan approximately 60 channels at approximately 4,500 tokens/page of 20; compare agent-mcp `get` at approximately 133 tokens). |
| search | Search Slack channels by keyword.<br>Agent requests id, name, num_members, is_archived, is_private, created, updated, topic, and purpose per result. | 🛑No native search/filter tool exists in [@modelcontextprotocol/server-slack](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack) ([v2025.4.25](https://www.npmjs.com/package/@modelcontextprotocol/server-slack)). All 8 tools: `slack_list_channels`, `slack_post_message`, `slack_reply_to_thread`, `slack_add_reaction`, `slack_get_channel_history`, `slack_get_thread_replies`, `slack_get_users`, `slack_get_user_profile`. None support keyword filtering on channel names. Alternative path: paginate `slack_list_channels` (all pages) and filter client-side by keyword (est. approximately 13,400 tokens to scan all approximately 60 channels at approximately 4,500 tokens/page of 20; must exhaust every page to find all matches). |

**Scenario definitions:** [slack-list-all](../../src/agent_bench/scenarios/slack-list-all.yaml) | [slack-get](../../src/agent_bench/scenarios/slack-get.yaml) | [slack-search](../../src/agent_bench/scenarios/slack-search.yaml)

### Zendesk

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Look up a single Zendesk ticket by ID.<br>Agent requests id, subject, status, and priority. | 💎Only requested fields consume token context: `id`, `subject`, `status`, and `priority`.; ℹ️ The agent-mcp connector syncs from a Zendesk instance containing ticket #17394, but the native MCP OAuth credentials connect to `d3v-airbyte.zendesk.com` which only has ticket #2. Each path fetches a valid single ticket from its respective instance; the benchmark measures token overhead, not data identity. |
| search | Search Zendesk tickets matching a keyword.<br>Agent requests id, subject, status, and priority per result. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 182 | 511 | 1 | 1 | 36% | 64% | 💎Only requested fields consume token context: `id`, `subject`, `status`, and `priority`.; ℹ️ The agent-mcp connector syncs from a Zendesk instance containing ticket #17394, but the native MCP OAuth credentials connect to `d3v-airbyte.zendesk.com` which only has ticket #2. Each path fetches a valid single ticket from its respective instance; the benchmark measures token overhead, not data identity. |
| search | 433 | 1,015 | 10 | 2 | 43% | 57% |  |

**Connector total:** Agent MCP uses 40% of Native MCP tokens (60% savings)

**Scenario definitions:** [zendesk-get](../../src/agent_bench/scenarios/zendesk-get.yaml) | [zendesk-search](../../src/agent_bench/scenarios/zendesk-search.yaml)

## Methodology

- **Agent MCP** uses `select_fields` to return only requested fields (typically 4-9 fields per record)
- **Native MCP** returns the vendor API's full response objects (typically 30-200+ fields per record)
- Token counts computed with tiktoken `cl100k_base` encoding on raw JSON response payloads
- Each scenario executes the same logical operation (search/get/list) on both paths

## Per-Connector Summary

> :warning: Please review detailed results above for necessary disclaimers, descriptions of issues, and other explanations.

| Connector | Agent MCP tokens | Native MCP tokens | Ratio | Savings |
|---|---:|---:|---:|---:|
| Gong | 195 | 279 | 70% | 30% |
| Linear | 1,207 | 1,355 | 89% | 11% |
| Multi_Source | 1,482 | 30,208 | 5% | 95% |
| Salesforce | 684 | 819 | 84% | 16% |
| Slack | 118,896 | 362,313 | 33% | 67% |
| Zendesk | 615 | 1,526 | 40% | 60% |
