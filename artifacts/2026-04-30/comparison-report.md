# Token Efficiency Comparison Report

**Date:** 2026-04-30  
**Compared paths:** Agent MCP vs Native MCP  
**Connectors:** Gong, Linear, Salesforce, Slack, Zendesk

## Per-Connector Summary

> :warning: Please review detailed results below for necessary disclaimers, descriptions of issues, and other explanations.

| Connector | Agent MCP tokens | Native MCP tokens | Ratio | Savings |
|---|---:|---:|---:|---:|
| Gong | 5,125 | 26,505 | 19% | 81% |
| Linear | 1,325 | 4,212 | 31% | 69% |
| Salesforce | 687 | 825 | 83% | 17% |
| Zendesk | 612 | 38,308 | 2% | 98% |

## Per-Scenario Breakdown

### Gong

#### Scenario Descriptions

| Action | Entities | Description | Annotations |
|---|---|---|---|
| search | calls | List Gong calls within a date range.<br>Agent requests id, title, scheduled, and duration per result. |  |

#### Scenario Benchmark Results

| Action | Entities | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| search | calls | 5,125 | 26,505 | 100 | 100 | 19% | 81% |  |

**Connector total:** Agent MCP uses 19% of Native MCP tokens (81% savings)

#### Benchmarks Not Comparable

These scenarios could not produce a valid comparison between Agent MCP and the vendor's native MCP server.

| Action | Entities | Description | Annotations |
|---|---|---|---|
| get | calls | Look up a single Gong call by ID.<br>Agent requests id, title, scheduled, and duration. | 💎Only requested fields consume token context: `id`, `title`, `scheduled`, and `duration`.; 🛑No native get-by-ID tool exists in [kenazk/gong-mcp](https://github.com/kenazk/gong-mcp). The server exposes only two tools: `list_calls` (date-range listing) and `retrieve_transcripts` (transcript text by call ID). Neither returns single-call metadata (id, title, scheduled, duration). The Gong REST API has `GET /v2/calls/{id}` but the MCP server does not wrap it. |

**Scenario definitions:** [gong-search](/src/agent_bench/scenarios/gong-search.yaml) | [gong-get](/src/agent_bench/scenarios/gong-get.yaml)

### Linear

#### Scenario Descriptions

| Action | Entities | Description | Annotations |
|---|---|---|---|
| get | issues | Look up a single Linear issue by ID.<br>Agent requests id, identifier, title, state, priority, createdAt, updatedAt, team, and labels. |  |
| search | issues | Search Linear issues by keyword.<br>Agent requests id, identifier, title, state, priority, createdAt, updatedAt, team, and labels per result. |  |

#### Scenario Benchmark Results

| Action | Entities | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| get | issues | 263 | 487 | 1 | 1 | 54% | 46% |  |
| search | issues | 1,062 | 3,725 | 8 | 8 | 29% | 71% |  |

**Connector total:** Agent MCP uses 31% of Native MCP tokens (69% savings)

#### Benchmarks Not Comparable

These scenarios could not produce a valid comparison between Agent MCP and the vendor's native MCP server.

| Action | Entities | Description | Annotations |
|---|---|---|---|
| search | projects | Search Linear projects by name keyword.<br>Agent requests id, name, state, and progress. | 🛑No native project search tool exists in Linear's official MCP server ([mcp.linear.app](https://linear.app/docs/mcp), 24 tools). `list_projects` returns all projects with no name filter parameter. `get_project` requires a project ID. The Linear GraphQL API supports `projects(filter: { name: { contains: "..." } })` ([filtering docs](https://linear.app/developers/filtering)), but the MCP does not expose this capability. Alternative path: call `list_projects` to retrieve all projects and filter client-side. |
| search | users | Search Linear workspace members by name.<br>Agent requests id, name, active, admin, and isMe. | 🛑No native user search tool exists in Linear's official MCP server ([mcp.linear.app](https://linear.app/docs/mcp), 24 tools). `list_users` returns all members with no name filter parameter. `get_user` requires a user ID. The Linear GraphQL API supports `users(filter: { name: { contains: "..." } })` ([filtering docs](https://linear.app/developers/filtering)), but the MCP does not expose this capability. Alternative path: call `list_users` to retrieve all workspace members and filter client-side. |

**Scenario definitions:** [linear-get](/src/agent_bench/scenarios/linear-get.yaml) | [linear-search](/src/agent_bench/scenarios/linear-search.yaml) | [linear-project-search](/src/agent_bench/scenarios/linear-project-search.yaml) | [linear-user-search](/src/agent_bench/scenarios/linear-user-search.yaml)

### Salesforce

#### Scenario Descriptions

| Action | Entities | Description | Annotations |
|---|---|---|---|
| get | accounts | Look up a single Salesforce account by ID.<br>Agent requests Id, Name, Type, and Industry. |  |
| search | accounts | Search Salesforce accounts matching a keyword.<br>Agent requests Id, Name, Type, and Industry per result. |  |

#### Scenario Benchmark Results

| Action | Entities | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| get | accounts | 178 | 90 | 1 | 1 | 198% | -98% |  |
| search | accounts | 509 | 735 | 10 | 10 | 69% | 31% |  |

**Connector total:** Agent MCP uses 83% of Native MCP tokens (17% savings)

**Scenario definitions:** [salesforce-get](/src/agent_bench/scenarios/salesforce-get.yaml) | [salesforce-search](/src/agent_bench/scenarios/salesforce-search.yaml)

### Slack

#### Benchmarks Not Comparable

These scenarios could not produce a valid comparison between Agent MCP and the vendor's native MCP server.

| Action | Entities | Description | Annotations |
|---|---|---|---|
| get | channels | Fetch a single Slack channel by ID.<br>Agent requests id, name, is_archived, is_private, created, updated, topic, and purpose. | ℹ️ The Slack connector's context store is not populated in the benchmark workspace. `context_store_search` with `eq: {id: "C02TD5CB7PZ"}` returns `data: []`. This scenario uses `action: get` as a direct lookup instead.; 🛑No native get-by-ID tool exists in [@modelcontextprotocol/server-slack](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack) ([v2025.4.25](https://www.npmjs.com/package/@modelcontextprotocol/server-slack)). All 8 tools: `slack_list_channels`, `slack_post_message`, `slack_reply_to_thread`, `slack_add_reaction`, `slack_get_channel_history`, `slack_get_thread_replies`, `slack_get_users`, `slack_get_user_profile`. None accept a channel ID and return a single channel. Alternative path: paginate `slack_list_channels` until the target channel is found (est. approximately 13,400 tokens to scan approximately 60 channels at approximately 4,500 tokens/page of 20; compare agent-mcp `get` at approximately 133 tokens). |

**Scenario definitions:** [slack-get](/src/agent_bench/scenarios/slack-get.yaml)

### Zendesk

#### Scenario Descriptions

| Action | Entities | Description | Annotations |
|---|---|---|---|
| get | tickets | Look up a single Zendesk ticket by ID.<br>Agent requests id, subject, status, and priority. | 💎Only requested fields consume token context: `id`, `subject`, `status`, and `priority`. |
| search | tickets | Search Zendesk tickets matching a keyword.<br>Agent requests id, subject, status, and priority per result. |  |

#### Scenario Benchmark Results

| Action | Entities | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| get | tickets | 181 | 4,002 | 1 | 1 | 5% | 95% | 💎Only requested fields consume token context: `id`, `subject`, `status`, and `priority`. |
| search | tickets | 431 | 34,306 | 10 | 10 | 1% | 99% |  |

**Connector total:** Agent MCP uses 2% of Native MCP tokens (98% savings)

**Scenario definitions:** [zendesk-get](/src/agent_bench/scenarios/zendesk-get.yaml) | [zendesk-search](/src/agent_bench/scenarios/zendesk-search.yaml)

## Methodology

- **Agent MCP** uses `select_fields` to return only requested fields (typically 4-9 fields per record)
- **Native MCP** returns the vendor API's full response objects (typically 30-200+ fields per record)
- Token counts computed with tiktoken `cl100k_base` encoding on raw JSON response payloads
- Each scenario executes the same logical operation on both paths (search or get)
- Multi-step scenarios chain recorded tool calls across connectors with statically seeded inputs. Results are replayed from committed recordings, not executed live. See [METHODOLOGY.md](/docs/METHODOLOGY.md#multi-step-scenarios) for details
