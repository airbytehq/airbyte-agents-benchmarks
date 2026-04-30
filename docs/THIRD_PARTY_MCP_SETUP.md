# Third-Party MCP Servers: Installation and Configuration

This document explains how to install and configure the native MCP servers provided by Linear, Granola, Slack, and Zendesk. These are the third-party alternatives the benchmark compares Airbyte Agents against.

The benchmark's `native-mcp` path uses recordings captured from these providers' MCP tools. To capture fresh recordings or independently verify tool call shapes, you need access to these servers.

## Overview

Each connector in the benchmark has a corresponding MCP server maintained by the service provider (or the MCP open-source project):

| Connector | MCP Server | Transport | Auth |
|---|---|---|---|
| Linear | `https://mcp.linear.app/mcp` | Streamable HTTP (remote) | OAuth 2.0 (browser flow) |
| Granola | `https://mcp.granola.ai/mcp` | Streamable HTTP (remote) | OAuth 2.0 (browser flow) |
| Slack | `@modelcontextprotocol/server-slack` | stdio (local, via `npx`) | Bot token + team ID |
| Zendesk | `reminia/zendesk-mcp-server` | stdio (local, via `uvx`) | Email + API token |

Linear and Granola run as remote hosted servers with browser-based OAuth. Slack and Zendesk run locally via subprocess with static credentials.

---

## Linear MCP

Linear provides an official remote MCP server at `https://mcp.linear.app/mcp`. It follows the authenticated remote MCP spec with OAuth 2.0 and dynamic client registration.

**Docs:** https://linear.app/docs/mcp

### Claude Code

```bash
claude mcp add --transport http linear-server https://mcp.linear.app/mcp
```

Then open a Claude Code session, run `/mcp`, select the Linear server, and complete the OAuth flow in your browser.

### Claude Desktop

Navigate to Settings > Connectors, search for Linear, and connect. Available on Team and Enterprise plans. On other paid plans, use Settings > Connectors in the Claude desktop app.

### Other MCP Clients (VS Code, Cursor, Windsurf, etc.)

For clients that do not support remote MCP natively, use `mcp-remote` as a bridge:

```json
{
  "mcpServers": {
    "linear": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.linear.app/mcp"]
    }
  }
}
```

### API Key Auth (Non-Interactive)

Linear also supports passing an API key directly via the `Authorization: Bearer` header instead of the interactive OAuth flow. Generate a key from Linear > Settings > Account > Security & Access > API Keys.

### Available Tools

The benchmark uses these Linear MCP tools (tool names as they appear in Claude Code):

| Benchmark Task | Tool | Example Args |
|---|---|---|
| search | `mcp__claude_ai_Linear__list_issues` | `{"query": "context store", "limit": 10}` |
| get | `mcp__claude_ai_Linear__get_issue` | `{"id": "AGENTIC-338"}` |
| list | `mcp__claude_ai_Linear__list_issues` | `{"limit": 50}` |

The Linear MCP server also provides tools for creating and updating issues, managing projects, and more. Only the read tools are relevant to this benchmark.

---

## Granola MCP

Granola provides an official remote MCP server at `https://mcp.granola.ai/mcp`. It uses Streamable HTTP transport with browser-based OAuth.

**Docs:** https://docs.granola.ai/help-center/sharing/integrations/mcp

### Prerequisites

- A Granola account with existing meeting notes
- A paid Claude or ChatGPT account (free-plan users can only query notes from the last 30 days)

### Claude Code

```bash
claude mcp add granola --transport http https://mcp.granola.ai/mcp
```

Then open a new terminal tab, run `claude`, then run `/mcp`, select the Granola MCP, and select "Authenticate" to complete the browser OAuth flow.

### Claude Desktop

Navigate to Settings > Connectors, search for Granola, and connect. You must authenticate via the browser when prompted.

### ChatGPT

Go to Settings, search for "Granola", and connect. You can then `@Granola` or just ask to reference your meetings.

### Other MCP Clients

For clients supporting Streamable HTTP, use the public URL `https://mcp.granola.ai/mcp` as a custom MCP connection. The client must support OAuth 2.0 browser-based authentication.

There is no API key or service account access method for Granola MCP. Each user authenticates individually through the browser OAuth flow.

### Available Tools

The benchmark's `claude` path records and replays the Claude Code tool names below. The underlying Granola MCP server tool names are included for reference.

| Benchmark Task | MCP Server Tool | Claude Code Tool | Description |
|---|---|---|---|
| search | `query_granola_meetings` | `mcp__claude_ai_Granola__query_granola_meetings` | Chat-style query; returns a synthesized natural-language answer, not structured records |
| get | `get_meeting_transcript` | `mcp__claude_ai_Granola__get_meeting_transcript` | Returns meeting ID, title, and full raw transcript (paid plans only) |
| list | `list_meetings` | `mcp__claude_ai_Granola__list_meetings` | Returns meeting ID, title, date, and attendees; no limit parameter |

Additional tools (not used by this benchmark):

| MCP Server Tool | Claude Code Tool | Description |
|---|---|---|
| `list_meeting_folders` | `mcp__claude_ai_Granola__list_meeting_folders` | List folders you are a member of (paid plans only) |
| `get_meetings` | `mcp__claude_ai_Granola__get_meetings` | Search through meeting content including notes and attendees |

Notable behavior:

- `query_granola_meetings` returns a synthesized answer, not raw records. This is a fundamentally different response shape from Agent MCP, which returns typed JSON.
- `list_meetings` has no limit parameter. It returns all meetings in the queried time range.
- `get_meeting_transcript` requires a meeting UUID. Airbyte Agents note IDs (`not_...`) are not UUIDs and need translation.
- Free-plan users are limited to notes from the last 30 days.
- Rate limits average approximately 100 requests per minute across all tools.

---

## Slack MCP

Slack has two MCP options. The benchmark uses the `@modelcontextprotocol/server-slack` package, which runs locally via `npx`.

**Package:** https://www.npmjs.com/package/@modelcontextprotocol/server-slack
**Slack official docs:** https://docs.slack.dev/ai/slack-mcp-server

### Prerequisites

- Node.js 18 or later with `npx`
- A Slack workspace where you can create or manage apps
- A Slack Bot Token (`xoxb-...`) with the required scopes
- Your Slack Team ID (starts with `T`)

### Step 1: Create a Slack App

1. Go to https://api.slack.com/apps
2. Click "Create New App" > "From scratch"
3. Name your app and select your workspace

### Step 2: Configure Bot Token Scopes

Navigate to "OAuth & Permissions" and add these bot scopes:

- `channels:history` — view messages in public channels
- `channels:read` — view basic channel information
- `chat:write` — send messages as the app
- `reactions:write` — add emoji reactions
- `users:read` — view users and basic info
- `users.profile:read` — view detailed user profiles

### Step 3: Install and Get Tokens

1. Click "Install to Workspace" and authorize
2. Copy the Bot User OAuth Token (starts with `xoxb-`)
3. Get your Team ID by following [Slack's guide](https://slack.com/help/articles/221769328-Locate-your-Slack-URL-or-ID#find-your-workspace-or-org-id)

### Claude Desktop / Claude Code Config

```json
{
  "mcpServers": {
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "xoxb-your-bot-token",
        "SLACK_TEAM_ID": "T01234567"
      }
    }
  }
}
```

Optionally add `SLACK_CHANNEL_IDS` (comma-separated) to restrict which channels the server can access.

### Available Tools

The Slack MCP server exposes server-native tool names that differ from the Claude Code tool names used by the benchmark harness. For `--tool`, use the benchmark-facing Claude Code names.

| MCP Server Tool | Claude Code / Benchmark Tool | Description |
|---|---|---|
| `slack_search_channels` | `mcp__claude_ai_Slack__slack_search_channels` | Search channels by name; the benchmark uses this for search, get, and list tasks |
| `slack_post_message` | `mcp__claude_ai_Slack__slack_post_message` | Post a message to a channel |
| `slack_reply_to_thread` | `mcp__claude_ai_Slack__slack_reply_to_thread` | Reply to a message thread |
| `slack_add_reaction` | `mcp__claude_ai_Slack__slack_add_reaction` | Add an emoji reaction |
| `slack_get_channel_history` | `mcp__claude_ai_Slack__slack_get_channel_history` | Get recent messages from a channel |
| `slack_get_thread_replies` | `mcp__claude_ai_Slack__slack_get_thread_replies` | Get all replies in a thread |
| `slack_get_users` | `mcp__claude_ai_Slack__slack_get_users` | List workspace users (max 200 per page) |
| `slack_get_user_profile` | `mcp__claude_ai_Slack__slack_get_user_profile` | Get detailed profile for a user |

The benchmark uses channel-oriented read tools. Notable limitations:

- There is no dedicated get-channel-by-ID tool. The benchmark falls back to `mcp__claude_ai_Slack__slack_search_channels` for all channel operations (search, get, and list).
- The search API caps at 20 results per page. The benchmark's list task issues multiple 20-result search calls to approximate a bulk list.
- The Slack MCP server is subject to Slack API rate limits (Tier 2: 20+ per minute for search, Tier 3: 50+ per minute for history).

### Alternative: Slack's Official Remote MCP

Slack also provides a hosted remote MCP server at `https://mcp.slack.com/mcp` (Streamable HTTP, OAuth 2.0). This requires a published or internal Slack app and uses user tokens with granular scopes. See https://docs.slack.dev/ai/slack-mcp-server for details. The benchmark does not currently use this server but it is an option for future evaluation.

---

## Zendesk MCP

The benchmark uses the community **dunialabs/mcp-zendesk** server (TypeScript, MIT, Docker image) via stdio transport. No official Zendesk MCP server exists.

**Repo:** https://github.com/dunialabs/mcp-servers/tree/main/mcp-zendesk
**Docker image:** `ghcr.io/dunialabs/mcp-servers/zendesk:latest`

### Prerequisites

- Docker
- A Zendesk OAuth access token (or email + API token for development)

### Environment Variables

The recording script loads credentials from 1Password (`zendesk-support` item, `test-credentials-oauth` section). For manual runs, set:

```bash
export ZENDESK_SUBDOMAIN="d3v-airbyte"
export ZENDESK_ACCESS_TOKEN="your-oauth-access-token"
```

### How the Recording Script Launches It

The `ZendeskMCP` class in `scripts/record_native_mcp.py` launches the Docker container with stdio transport:

```bash
docker run -i --rm \
  -e zendeskSubdomain=d3v-airbyte \
  -e accessToken=$ZENDESK_ACCESS_TOKEN \
  ghcr.io/dunialabs/mcp-servers/zendesk:latest
```

The container reads JSON-RPC messages from stdin and writes responses to stdout.

### Available Tools

| Benchmark Task | MCP Tool | Args | Description |
|---|---|---|---|
| search | `zendeskSearchTickets` | `{"query": "status:open"}` | Search tickets using Zendesk query syntax |
| get | `zendeskGetTicket` | `{"ticket_id": 2}` | Retrieve a single ticket by ID |
| list | `zendeskListTickets` | `{}` | List recent tickets (default 25) |

The server exposes 18 tools total (ticket, user, and organization management). The benchmark uses only the three ticket read operations listed above.

---

## Using These Servers With the Benchmark

### Replaying Committed Recordings

You do not need to install any third-party MCP server to replay existing recordings. The committed recordings at `artifacts/2026-04-24/{scenario}-scenario/native-mcp/recording.json` are self-contained JSON files that the harness reads directly:

```bash
uv run agent-bench run --scenarios linear,granola --paths native-mcp
uv run agent-bench validate --scenarios linear,granola --paths native-mcp
```

### Capturing Fresh Recordings

To capture new recordings, you need the relevant MCP server configured and accessible in Claude Code (or another MCP client). The workflow is:

1. Configure the MCP server (see sections above).
2. Invoke the tool call in your MCP client and copy the raw JSON response to a file.
3. Use the helper script to save the recording:

```bash
uv run python scripts/record_response.py \
  --path native-mcp \
  --scenario linear-search \
  --tool mcp__claude_ai_Linear__list_issues \
  --args '{"query": "context store", "limit": 10}' \
  --wall-ms 0 \
  --response-file /tmp/response.json \
  --reset
```

For `native-mcp` path recordings, `--wall-ms` is required. Use `0` if you are not measuring latency (this is the convention in this benchmark since native MCP latency is not captured).

The `--tool` and `--args` values must match the tool call shapes shown in the Available Tools tables above.

### Recording File Format

Each recording file is a JSON array of objects:

```json
[
  {
    "tool": "mcp__claude_ai_Linear__list_issues",
    "args": {"query": "context store", "limit": 10},
    "wall_clock_ms": 0,
    "response": { ... }
  }
]
```

Some tasks (e.g., Slack list) produce multiple calls per recording file. Use `--reset` to start fresh or omit it to append additional calls.

---

## Comparison With Agent MCP

| Dimension | Third-Party MCP | Agent MCP (`agent-mcp`) |
|---|---|---|
| Servers | One per service (Linear, Granola, Slack, Zendesk) | Unified `mcp__airbyte-agent__execute` |
| Auth | Per-service (OAuth, bot tokens, or API keys) | Single Airbyte Cloud OAuth credential set |
| Field selection | Not available; full responses returned | `select_fields` narrows returned fields |
| Response shape | Varies by provider (JSON, text, markdown) | Uniform typed JSON envelope |
| Hosting | Remote (Linear, Granola) or local (Slack, Zendesk) | Airbyte-hosted proxy at `mcp.airbyte.ai` |
