# Token Efficiency Comparison Report

**Date:** 2026-04-29  
**Compared paths:** Agent MCP vs Native MCP  
**Connectors:** Gong, Linear, Salesforce, Slack, Zendesk

## Per-Scenario Breakdown

### Gong

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Gong call by ID.<br>Agent requests id, title, scheduled, and duration. | 💎 Equal record counts; savings driven purely by field selection. |
| list | List the most recent Gong calls.<br>Agent requests id, title, scheduled, and duration per record. | 💎 Equal record counts; savings driven purely by field selection. |
| search | Search Gong calls matching a keyword.<br>Agent requests id, title, scheduled, and duration per result. | ℹ️ Unequal record counts amplify the ratio. Per-record savings are real. |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 51 | 281 | 1 | 1 | 18% | 82% | 💎 Equal record counts; savings driven purely by field selection. |
| list | 5,147 | 26,080 | 100 | 100 | 20% | 80% | 💎 Equal record counts; savings driven purely by field selection. |
| search | 529 | 26,578 | 10 | 100 | 2% | 98% | ℹ️ Unequal record counts amplify the ratio. Per-record savings are real. |

**Connector total:** Agent MCP uses 11% of Native MCP tokens (89% savings)

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
| get | 163 | 311 | 1 | 1 | 52% | 48% |  |
| list | 8,208 | 17,403 | 50 | 50 | 47% | 53% |  |
| search | 847 | 1,044 | 7 | 3 | 81% | 19% |  |

**Connector total:** Agent MCP uses 49% of Native MCP tokens (51% savings)

### Salesforce

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Salesforce account by ID.<br>Agent requests Id, Name, Type, and Industry. | ℹ️ Different Salesforce orgs (zero overlapping IDs). Both perform a valid single-Account get. |
| list | List Salesforce accounts via SOQL.<br>Agent requests Id, Name, Type, and Industry per record. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 36 | 864 | 1 | 1 | 4% | 96% | ℹ️ Different Salesforce orgs (zero overlapping IDs). Both perform a valid single-Account get. |
| list | 1,972 | 3,091 | 50 | 43 | 64% | 36% |  |

**Connector total:** Agent MCP uses 51% of Native MCP tokens (49% savings)

#### Benchmarks Not Comparable

These scenarios could not produce a valid comparison between Agent MCP and the vendor's native MCP server.

| Action | Description | Annotations |
|---|---|---|
| search | Search Salesforce accounts matching a keyword.<br>Agent requests Id, Name, Type, and Industry per result. | 🛑 Native SOSL returned 0 results; agent-mcp returned 10. Comparison invalid. Next step: Modify scenario to use valid query in Vendor MCP. |

### Slack

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| list | List the first 50 Slack channels.<br>Agent requests id, name, num_members, is_archived, is_private, created, updated, topic, and purpose per record. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| list | 6,858 | 13,416 | 50 | 36 | 51% | 49% |  |

**Connector total:** Agent MCP uses 51% of Native MCP tokens (49% savings)

#### Benchmarks Not Comparable

These scenarios could not produce a valid comparison between Agent MCP and the vendor's native MCP server.

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Slack channel by ID.<br>Agent requests id, name, num_members, is_archived, is_private, created, updated, topic, and purpose. | 🛑 No native get-by-ID tool exists; vendor MCP only exposes list_channels. |
| search | Search Slack channels by keyword.<br>Agent requests id, name, num_members, is_archived, is_private, created, updated, topic, and purpose per result. | 🛑 No native search tool exists; vendor MCP only exposes list_channels. Next step: Re-record with query matching a real channel name. |

### Zendesk

#### Scenario Descriptions

| Action | Description | Annotations |
|---|---|---|
| get | Fetch a single Zendesk ticket by ID.<br>Agent requests id, subject, status, and priority. | 💎 Equal record counts; savings driven purely by field selection. |
| list | List recent Zendesk tickets.<br>Agent requests id, subject, status, and priority per record. | 💎 Agent returned more records with fewer tokens. |
| search | Search Zendesk tickets matching a keyword.<br>Agent requests id, subject, status, and priority per result. |  |

#### Scenario Benchmark Results

| Action | Agent MCP tokens | Native MCP tokens | Agent MCP records | Native MCP records | Ratio | Savings | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| get | 26 | 514 | 1 | 1 | 5% | 95% | 💎 Equal record counts; savings driven purely by field selection. |
| list | 3,461 | 24,626 | 100 | 50 | 14% | 86% | 💎 Agent returned more records with fewer tokens. |
| search | 329 | 1,033 | 10 | 2 | 32% | 68% |  |

**Connector total:** Agent MCP uses 15% of Native MCP tokens (85% savings)

## Methodology

- **Agent MCP** uses `select_fields` to return only requested fields (typically 4-9 fields per record)
- **Native MCP** returns the vendor API's full response objects (typically 30-200+ fields per record)
- Token counts computed with tiktoken `cl100k_base` encoding on raw JSON response payloads
- Each scenario executes the same logical operation (search/get/list) on both paths

## Per-Connector Summary

> :warning: Please review detailed results above for necessary disclaimers, descriptions of issues, and other explanations.

| Connector | Agent MCP tokens | Native MCP tokens | Ratio | Savings |
|---|---:|---:|---:|---:|
| Gong | 5,727 | 52,939 | 11% | 89% |
| Linear | 9,218 | 18,758 | 49% | 51% |
| Salesforce | 2,008 | 3,955 | 51% | 49% |
| Slack | 6,858 | 13,416 | 51% | 49% |
| Zendesk | 3,816 | 26,173 | 15% | 85% |
