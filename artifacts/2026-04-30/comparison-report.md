# Token Efficiency Comparison Report

**Date:** 2026-04-30  
**Compared paths:** Agent MCP vs Native MCP  
**Connectors:** Gong, Gong-To-Salesforce-Zendesk, Linear, Salesforce, Slack, Zendesk

## Per-Scenario Breakdown

### Gong

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Gong call by ID.<br>Agent requests id, title, scheduled, and duration. | 💎Only requested fields consume token context: `id`, `title`, `scheduled`, and `duration`. |
| list | List the most recent Gong calls.<br>Agent requests id, title, scheduled, and duration per record. | 💎Only requested fields consume token context: `id`, `title`, `scheduled`, and `duration`. |
| search | Search Gong calls matching a keyword.<br>Agent requests id, title, scheduled, and duration per result. | ℹ️Unequal record counts amplify the ratio. Per-record savings are proportional to get/list. |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 160 | 278 | 1 | 1 | 58% | 42% | 💎Only requested fields consume token context: `id`, `title`, `scheduled`, and `duration`. |
| list | 5,436 | 26,084 | 100 | 100 | 21% | 79% | 💎Only requested fields consume token context: `id`, `title`, `scheduled`, and `duration`. |
| search | 638 | 26,584 | 10 | 100 | 2% | 98% | ℹ️Unequal record counts amplify the ratio. Per-record savings are proportional to get/list. |

**Connector total:** Agent MCP uses 12% of Native MCP tokens (88% savings)

**Scenario definitions:** [gong-get](../../src/agent_bench/scenarios/gong-get.yaml) | [gong-list](../../src/agent_bench/scenarios/gong-list.yaml) | [gong-search](../../src/agent_bench/scenarios/gong-search.yaml)

### Gong-To-Salesforce-Zendesk

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| lookup | Multi-step cross-connector workflow: search for Gong calls scheduled<br>on 2026-04-28, then look up the associated account names in Salesforce and<br>find open tickets for those accounts in Zendesk.<br>Steps 2 and 3 use dummy static account/ticket lists to demonstrate<br>the choreographed multi-step scenario format. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| lookup | 1,486 | 30,208 | 22 | 145 | 5% | 95% |  |

**Connector total:** Agent MCP uses 5% of Native MCP tokens (95% savings)

<details><summary>Per-tool-call breakdown: Cross-system: Gong calls on 2026-04-28 → Salesforce + Zendesk lookup</summary>

**Agent MCP** (3 calls)

| Step | Server | Tool | Tokens | Records |
|---:|---|---|---:|---:|
| 1 | airbyte-agent | integrations_connectors_id_execute | 1,146 | 20 |
| 2 | airbyte-agent | integrations_connectors_id_execute | 210 | 2 |
| 3 | airbyte-agent | integrations_connectors_id_execute | 130 | 0 |

**Native MCP** (3 calls)

| Step | Server | Tool | Tokens | Records |
|---:|---|---|---:|---:|
| 1 | gong | list_calls | 26,084 | 100 |
| 2 | salesforce | soql_query | 3,091 | 43 |
| 3 | zendesk | search_tickets | 1,033 | 2 |

</details>

**Scenario definitions:** [gong-to-salesforce-zendesk-lookup](../../src/agent_bench/scenarios/gong-to-salesforce-zendesk-lookup.yaml)

### Linear

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Linear issue by ID.<br>Agent requests id, identifier, title, state, priority, createdAt, updatedAt, team, and labels. |  |
| list | List the first 50 Linear issues.<br>Agent requests id, identifier, title, state, priority, createdAt, updatedAt, team, and labels per record. |  |
| search | Search Linear issues by keyword.<br>Agent requests id, identifier, title, state, priority, createdAt, updatedAt, team, and labels per result. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 274 | 311 | 1 | 1 | 88% | 12% |  |
| list | 8,374 | 17,403 | 50 | 50 | 48% | 52% |  |
| search | 958 | 1,044 | 7 | 3 | 92% | 8% |  |

**Connector total:** Agent MCP uses 51% of Native MCP tokens (49% savings)

**Scenario definitions:** [linear-get](../../src/agent_bench/scenarios/linear-get.yaml) | [linear-list](../../src/agent_bench/scenarios/linear-list.yaml) | [linear-search](../../src/agent_bench/scenarios/linear-search.yaml)

### Salesforce

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Salesforce account by ID.<br>Agent requests Id, Name, Type, and Industry.<br>Note: agent-mcp and native-mcp use different account IDs because<br>they connect to different Salesforce orgs. |  |
| list | List Salesforce accounts via SOQL.<br>Agent requests Id, Name, Type, and Industry per record. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 141 | 90 | 1 | 1 | 157% | -57% |  |
| list | 2,086 | 3,091 | 50 | 43 | 67% | 33% |  |

**Connector total:** Agent MCP uses 70% of Native MCP tokens (30% savings)

#### Benchmarks Not Comparable

These scenarios could not produce a valid comparison between Agent MCP and the vendor's native MCP server.

| Action | Description | Annotations |
|---|---|---|
| search | Search Salesforce accounts matching a keyword.<br>Agent requests Id, Name, Type, and Industry per result. | 🛑Native SOSL returned 0 results; agent-mcp returned 10. Comparison invalid. Root causes: (1) Different Salesforce orgs between agent-mcp and native-mcp — no overlapping data (org alignment fix in progress). (2) [SOSL](https://developer.salesforce.com/docs/atlas.en-us.soql_sosl.meta/soql_sosl/sforce_api_calls_sosl.htm) relies on a full-text search index with [known indexing delays](https://issues.salesforce.com/issue/a028c00000j5kNRAAY) (up to 15-30 min for new records) and tokenization quirks that can return 0 results even when data exists. If SOSL remains unreliable after org alignment, SOQL `WHERE Name LIKE '%airbyte%'` queries the database directly and bypasses the search index (est. approximately 720 tokens for approximately 10 matching records at approximately 72 tokens/record, based on salesforce-list native-mcp rate). Next step: Modify scenario to use valid query in Vendor MCP. |

**Scenario definitions:** [salesforce-get](../../src/agent_bench/scenarios/salesforce-get.yaml) | [salesforce-list](../../src/agent_bench/scenarios/salesforce-list.yaml) | [salesforce-search](../../src/agent_bench/scenarios/salesforce-search.yaml)

### Slack

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| list | List the first 50 Slack channels.<br>Agent requests id, name, num_members, is_archived, is_private, created, updated, topic, and purpose per record. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| list | 6,985 | 13,416 | 50 | 36 | 52% | 48% |  |

**Connector total:** Agent MCP uses 52% of Native MCP tokens (48% savings)

<details><summary>Per-tool-call breakdown: Slack — List first 50 channels</summary>

**Agent MCP** (1 calls)

| Step | Server | Tool | Tokens | Records |
|---:|---|---|---:|---:|
| 1 | airbyte-agent | integrations_connectors_id_execute | 6,985 | 50 |

**Native MCP** (3 calls)

| Step | Server | Tool | Tokens | Records |
|---:|---|---|---:|---:|
| 1 | slack | slack_list_channels | 4,472 | 12 |
| 2 | slack | slack_list_channels | 4,472 | 12 |
| 3 | slack | slack_list_channels | 4,472 | 12 |

</details>

#### Benchmarks Not Comparable

These scenarios could not produce a valid comparison between Agent MCP and the vendor's native MCP server.

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Slack channel by ID.<br>Agent requests id, name, num_members, is_archived, is_private, created, updated, topic, and purpose. | 🛑No native get-by-ID tool exists in [@modelcontextprotocol/server-slack](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack) ([v2025.4.25](https://www.npmjs.com/package/@modelcontextprotocol/server-slack)). All 8 tools: `slack_list_channels`, `slack_post_message`, `slack_reply_to_thread`, `slack_add_reaction`, `slack_get_channel_history`, `slack_get_thread_replies`, `slack_get_users`, `slack_get_user_profile`. None accept a channel ID and return a single channel. Alternative path: paginate `slack_list_channels` until the target channel is found (est. approximately 13,400 tokens to scan approximately 60 channels at approximately 4,500 tokens/page of 20; compare agent-mcp `get` at approximately 133 tokens). |
| search | Search Slack channels by keyword.<br>Agent requests id, name, num_members, is_archived, is_private, created, updated, topic, and purpose per result. | 🛑No native search/filter tool exists in [@modelcontextprotocol/server-slack](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack) ([v2025.4.25](https://www.npmjs.com/package/@modelcontextprotocol/server-slack)). All 8 tools: `slack_list_channels`, `slack_post_message`, `slack_reply_to_thread`, `slack_add_reaction`, `slack_get_channel_history`, `slack_get_thread_replies`, `slack_get_users`, `slack_get_user_profile`. None support keyword filtering on channel names. Alternative path: paginate `slack_list_channels` (all pages) and filter client-side by keyword (est. approximately 13,400 tokens to scan all approximately 60 channels at approximately 4,500 tokens/page of 20; must exhaust every page to find all matches). |

**Scenario definitions:** [slack-list](../../src/agent_bench/scenarios/slack-list.yaml) | [slack-get](../../src/agent_bench/scenarios/slack-get.yaml) | [slack-search](../../src/agent_bench/scenarios/slack-search.yaml)

### Zendesk

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Zendesk ticket by ID.<br>Agent requests id, subject, status, and priority. | 💎Only requested fields consume token context: `id`, `subject`, `status`, and `priority`. |
| list | List recent Zendesk tickets.<br>Agent requests id, subject, status, and priority per record. | 💎Agent returned more records with fewer tokens. |
| search | Search Zendesk tickets matching a keyword.<br>Agent requests id, subject, status, and priority per result. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 130 | 514 | 1 | 1 | 25% | 75% | 💎Only requested fields consume token context: `id`, `subject`, `status`, and `priority`. |
| list | 3,600 | 24,626 | 100 | 50 | 15% | 85% | 💎Agent returned more records with fewer tokens. |
| search | 431 | 1,033 | 10 | 2 | 42% | 58% |  |

**Connector total:** Agent MCP uses 16% of Native MCP tokens (84% savings)

**Scenario definitions:** [zendesk-get](../../src/agent_bench/scenarios/zendesk-get.yaml) | [zendesk-list](../../src/agent_bench/scenarios/zendesk-list.yaml) | [zendesk-search](../../src/agent_bench/scenarios/zendesk-search.yaml)

## Methodology

- **Agent MCP** uses `select_fields` to return only requested fields (typically 4-9 fields per record)
- **Native MCP** returns the vendor API's full response objects (typically 30-200+ fields per record)
- Token counts computed with tiktoken `cl100k_base` encoding on raw JSON response payloads
- Each scenario executes the same logical operation (search/get/list) on both paths

## Per-Connector Summary

> :warning: Please review detailed results above for necessary disclaimers, descriptions of issues, and other explanations.

| Connector | Agent MCP tokens | Native MCP tokens | Ratio | Savings |
|---|---:|---:|---:|---:|
| Gong | 6,234 | 52,946 | 12% | 88% |
| Gong-To-Salesforce-Zendesk | 1,486 | 30,208 | 5% | 95% |
| Linear | 9,606 | 18,758 | 51% | 49% |
| Salesforce | 2,227 | 3,181 | 70% | 30% |
| Slack | 6,985 | 13,416 | 52% | 48% |
| Zendesk | 4,161 | 26,173 | 16% | 84% |
