# Third-Party MCP Servers: Installation and Configuration

This document explains how to install and configure the native MCP servers used for benchmarking. These are the third-party alternatives the benchmark compares Airbyte Agents against.

The benchmark's `native-mcp` path uses recordings captured from these providers' MCP tools. To capture fresh recordings or independently verify tool call shapes, you need access to these servers.

## Overview

Each connector in the benchmark has a corresponding MCP server maintained by the service provider (or the MCP open-source project):

| Connector | MCP Server | Transport | Auth |
|---|---|---|---|
| Linear | `https://mcp.linear.app/mcp` | Streamable HTTP (remote) | OAuth 2.0 (browser flow) or API key |
| Slack | `https://mcp.slack.com/mcp` | Streamable HTTP (remote) | OAuth 2.0 (user token) |
| Zendesk | `ghcr.io/dunialabs/mcp-servers/zendesk` | stdio (local, via Docker) | OAuth access token |
| Gong | `kenazk/gong-mcp` | stdio (local, via Node.js) | Basic (access key + secret) |
| Salesforce | `api.salesforce.com/platform/mcp` | SSE (remote) | OAuth 2.0 (refresh token) |

Linear, Slack, and Salesforce all run as remote hosted servers. Linear uses browser-based OAuth; Slack and Salesforce use OAuth 2.0 with a custom app (a Slack app and a Salesforce Connected App, respectively). Zendesk runs locally via Docker with an OAuth access token.

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

## Slack MCP

The benchmark uses Slack's official hosted MCP server at `https://mcp.slack.com/mcp` (Streamable HTTP, JSON-RPC 2.0, OAuth 2.0). Authenticating requires creating a Slack app in your workspace, enabling the Model Context Protocol toggle, adding User Token Scopes, and minting a User OAuth Token (`xoxp-...`).

**Slack official docs:** https://docs.slack.dev/ai/slack-mcp-server

### Prerequisites

- A Slack workspace where you can create or manage apps
- Permission to install/reinstall the app in that workspace

### Step 1: Create a Slack App

1. Go to https://api.slack.com/apps
2. Click "Create New App" > "From scratch"
3. Name your app (e.g., "agent-bench-mcp") and select your workspace

### Step 2: Enable Model Context Protocol

1. In the app settings sidebar, open the **App Assistant** page
2. Scroll to the **Model Context Protocol** section and toggle it **on**
3. Save if prompted

> **Watch out:** the same page also has a separate **Agent or Assistant** toggle near the top. That is *not* the MCP toggle — flipping it has no effect on `mcp.slack.com/mcp` and you'll still get `App is not enabled for Slack MCP server access` errors. The MCP toggle is further down the page, in its own **Model Context Protocol** card.

### Step 3: Add User Token Scopes

The hosted MCP requires *user* token scopes (not bot scopes — bot tokens are not accepted). Navigate to **OAuth & Permissions** > **User Token Scopes** and add:

- `search:read.public` — search public channel content
- `search:read.private` — search private channel content
- `search:read.users` — search users by name/email/profile attributes
- `users:read` — read workspace member directory
- `users:read.email` — read member email addresses

(Slack's umbrella `search:read` scope also covers the three `search:read.*` entries; either choice works.)

### Step 4: Install and Get the User OAuth Token

1. Sidebar > **Install App** > click **Install to Workspace** (or **Reinstall to Workspace** if you've changed scopes)
2. Approve the consent screen
3. Copy the **User OAuth Token** at the top of the page — it starts with `xoxp-...`

> **Watch out:** any time you change scopes or toggle MCP on/off, you must **reinstall** the app for the existing tokens to pick up the new capability. A token minted before MCP was enabled will continue to return `App is not enabled for Slack MCP server access` until you reinstall.

### Step 4b: Verify the Token Works

Quick smoke test before wiring it into the recorder:

```bash
curl -sS -X POST https://mcp.slack.com/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer $SLACK_USER_OAUTH_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0.1"}}}'
```

A successful response includes `"serverInfo":{"name":"Slack MCP",...}` and a `mcp-session-id` header. Common failures:

| Error | Cause |
|---|---|
| `missing_token` | `Authorization` header not sent or empty |
| `App is not enabled for Slack MCP server access` | MCP toggle off, or app not reinstalled after enabling |
| `invalid_auth` | Token revoked, app uninstalled, or token from a different workspace |

### Step 5: Configure the Recorder

Add the token to your `.env` profile:

```
SLACK_USER_OAUTH_TOKEN=xoxp-...
```

The recorder reads only from `.env` (see `.env.template` for the full list of credential fields). If you keep credentials in 1Password, store this one under the `slack` item, section `test-credentials-mcp`, field `user_oauth_token`, and run `agent-bench populate-env` to sync it down to `.env`.

### Available Tools

The benchmark exercises two of the hosted MCP's tools:

| MCP Server Tool | Benchmark Tool | Description |
|---|---|---|
| `slack_search_channels` | `mcp__slack__slack_search_channels` | Search channels by name/description (cursor-paginated, max 20/call). Used by `slack-search` and the search-then-filter fallback for `slack-get`. |
| `slack_search_users` | `mcp__slack__slack_search_users` | Search users by name, email, or profile attributes (cursor-paginated, max 20/call). Used by `slack-user-search`. |

Notable limitations of the hosted MCP:

- **No get-channel-by-ID tool.** The `slack-get` scenario has no clean native counterpart and falls back to a search-then-filter approximation in the planner.
- Search results are capped at 20 per call across both `slack_search_channels` and `slack_search_users`.

The hosted MCP also exposes message-search, channel-read, thread-read, canvas, and chat-write tools (gated by `channels:history`, `chat:write`, `canvases:*`, etc.) — the benchmark does not use them today.

---

## Zendesk MCP

The benchmark uses the community **dunialabs/mcp-zendesk** server (TypeScript, MIT, Docker image) via stdio transport. No official Zendesk MCP server exists.

**Repo:** https://github.com/dunialabs/mcp-servers/tree/main/mcp-zendesk
**Docker image:** `ghcr.io/dunialabs/mcp-servers/zendesk:latest`

### Prerequisites

- Docker
- A Zendesk OAuth access token (or email + API token for development)

### Environment Variables

The recording script prefers environment variables from the active `.env` profile, falling back to 1Password (`zendesk-support` item, `test-credentials-oauth` section). Set these in your `.env` profile:

```bash
ZENDESK_SUBDOMAIN=your-subdomain
ZENDESK_ACCESS_TOKEN=your-oauth-access-token
ZENDESK_REFRESH_TOKEN=your-refresh-token
ZENDESK_CLIENT_ID=your-client-id
ZENDESK_CLIENT_SECRET=your-client-secret
```

See `.env.template` for the full list of credential fields.

### How the Recording Script Launches It

The `ZendeskMCP` class in `src/agent_bench/recording/native_mcp_recorder.py` launches the Docker container with stdio transport:

```bash
docker run -i --rm \
  -e zendeskSubdomain=$ZENDESK_SUBDOMAIN \
  -e accessToken=$ZENDESK_ACCESS_TOKEN \
  ghcr.io/dunialabs/mcp-servers/zendesk:latest
```

The container reads JSON-RPC messages from stdin and writes responses to stdout.

### Available Tools

| Benchmark Task | MCP Tool | Args | Description |
|---|---|---|---|
| search | `zendeskSearchTickets` | `{"query": "sync"}` | Search tickets using Zendesk query syntax |
| get | `zendeskGetTicket` | `{"ticket_id": 2}` | Retrieve a single ticket by ID |
| list | `zendeskListTickets` | `{}` | List recent tickets (default 25) |

The server exposes 18 tools total (ticket, user, and organization management). The benchmark uses only the three ticket read operations listed above.

---

## Salesforce MCP

Salesforce provides official hosted MCP servers at `api.salesforce.com`. The benchmark uses the **SObject Reads** server, which supports read-only SOQL queries and SOSL searches.

**Docs:** https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/client-connection-overview.html
**Server reference:** https://developer.salesforce.com/docs/platform/hosted-mcp-servers/references/reference/servers-reference.html

### Server URL

```
https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads
```

### Prerequisites

- A Salesforce org with API access enabled (production, not Developer Edition)
- An External Client App configured for MCP access (see below)
- OAuth credentials: `consumer_key` (client ID), `consumer_secret`, and a `refresh_token`

### Key Details for Airbyte's Salesforce Org

- **Org domain:** `airbyte.my.salesforce.com` (always use this, never `login.salesforce.com`)
- **MCP Home:** `https://airbyte.my.salesforce-setup.com/lightning/setup/McpServer/home`
- **External Client App config:** `https://airbyte.my.salesforce-setup.com/lightning/setup/ManageExternalClientApplication/0xIUJ0000000cA9/detail`
- **App name:** "Salesforce MCP (Internal Access)" (stored in 1Password `direct-connector-credentials` vault, `salesforce` item, section `test-credentials-mcp`)
- **Callback URL configured in the app:** `https://claude.ai/api/mcp/auth_callback`

### Authentication

The benchmark authenticates via the OAuth 2.0 refresh token flow. The recording script exchanges the refresh token for an access token at `https://airbyte.my.salesforce.com/services/oauth2/token`, then passes the access token as a `Bearer` token to the MCP server.

**Required environment variables:**

```bash
export SF_MCP_CONSUMER_KEY="your-connected-app-consumer-key"
export SF_MCP_CONSUMER_SECRET="your-connected-app-consumer-secret"
export SF_MCP_REFRESH_TOKEN="your-oauth-refresh-token"
```

These are set in your `.env` profile (e.g., `.env.dallas-prod`). Consumer key and secret are also available from 1Password (`salesforce` item, section `test-credentials-mcp`).

### Setting Up an External Client App

Salesforce recommends **External Client Apps** (not legacy Connected Apps) for MCP connections. To create one:

1. Follow the [Salesforce MCP setup guide](https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/create-external-client-app.html)
2. Set the callback URL to match your MCP client (e.g., `https://claude.ai/api/mcp/auth_callback` for Claude)
3. The app will be assigned a **Consumer Key** and **Consumer Secret** automatically

> **Important:** External Client Apps require PKCE (Proof Key for Code Exchange) for the authorization code flow. You must include `code_challenge` and `code_challenge_method=S256` parameters in the authorize URL, and `code_verifier` in the token exchange.

### Obtaining a Refresh Token

After creating the External Client App, generate a refresh token via the OAuth 2.0 Authorization Code flow with PKCE:

**Step 1: Generate a PKCE code verifier and challenge:**

```python
import secrets, hashlib, base64

verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(
    hashlib.sha256(verifier.encode()).digest()
).rstrip(b"=").decode()
print(f"VERIFIER={verifier}")
print(f"CHALLENGE={challenge}")
```

Save these values — you need the verifier for the token exchange in Step 4.

**Step 2: Open the authorize URL in your browser:**

Replace `YOUR_CONSUMER_KEY` and `YOUR_CHALLENGE` with your values:

```
https://airbyte.my.salesforce.com/services/oauth2/authorize?response_type=code&client_id=YOUR_CONSUMER_KEY&redirect_uri=https://claude.ai/api/mcp/auth_callback&code_challenge=YOUR_CHALLENGE&code_challenge_method=S256
```

> **Important:** Always use the org-specific domain (`airbyte.my.salesforce.com`), never `login.salesforce.com`. Using `login.salesforce.com` may route to the wrong org or fail with `redirect_uri_mismatch`.

> **Important:** The `redirect_uri` must exactly match the callback URL configured in the External Client App. For Airbyte's app, this is `https://claude.ai/api/mcp/auth_callback`.

> **Important:** Do not pass explicit `scope` parameters. External Client Apps use pre-configured scopes. Passing `scope=api+refresh_token` will fail with `invalid_scope`. The app's configured scopes (`refresh_token mcp_api`) are applied automatically.

**Step 3: Log in and authorize the app.** After authorization, the browser redirects to the callback URL with an authorization code in the query string:

```
https://claude.ai/api/mcp/auth_callback?code=AUTH_CODE_HERE
```

Claude's server may show an error (missing `state` parameter) — that's fine. Copy the `code` value from the URL before the page finishes loading.

**Step 4: Exchange the authorization code for tokens:**

```bash
curl -X POST https://airbyte.my.salesforce.com/services/oauth2/token \
  -d "grant_type=authorization_code" \
  -d "client_id=YOUR_CONSUMER_KEY" \
  -d "client_secret=YOUR_CONSUMER_SECRET" \
  -d "redirect_uri=https://claude.ai/api/mcp/auth_callback" \
  -d "code=AUTH_CODE_HERE" \
  -d "code_verifier=YOUR_VERIFIER"
```

The response includes `access_token`, `refresh_token`, `instance_url`, and `scope`. Save the `refresh_token` to your `.env` profile as `SF_MCP_REFRESH_TOKEN`.

### Troubleshooting

- **`redirect_uri_mismatch`**: The `redirect_uri` in the authorize URL must exactly match what's configured in the External Client App. Check the app config page linked above.
- **`invalid_scope`**: Do not pass `scope` parameter for External Client Apps. Scopes are pre-configured in the app.
- **`app_not_found`**: The External Client App is not installed in the Salesforce org you're authenticating against. Make sure you're using `airbyte.my.salesforce.com`, not a Developer Edition org like `airbyte-dev-ed`.
- **`missing required code_challenge`**: External Client Apps require PKCE. Include `code_challenge` and `code_challenge_method=S256` in the authorize URL.
- **401 from hosted MCP endpoint**: The access token must come from a production org with MCP access enabled. Developer Edition orgs (`airbyte-dev-ed`) do not have access to `api.salesforce.com/platform/mcp`.

### How the Recording Script Uses It

The `SalesforceMCP` class in `src/agent_bench/recording/native_mcp_recorder.py` connects to the hosted MCP server using Streamable HTTP transport:

1. Exchanges the refresh token for an access token via `airbyte.my.salesforce.com`
2. Sends a JSON-RPC `initialize` request to the MCP server URL
3. Receives an `mcp-session-id` header for subsequent requests
4. Calls tools via JSON-RPC `tools/call` requests with the session header

### Claude Desktop / Claude Code

Salesforce hosted MCP servers support native OAuth with Claude. Add via Claude Code:

```bash
claude mcp add --transport http salesforce-reads https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads
```

Then complete the OAuth flow in your browser when prompted. See [Salesforce's Claude configuration guide](https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/configure-claude.html) for details.

### Other MCP Clients (Cursor, Postman, etc.)

For clients that support OAuth 2.0 with PKCE, point them at the server URL and your External Client App's consumer key. Salesforce has tested with Claude, ChatGPT, Cursor, and Postman. See the [client connection overview](https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/client-connection-overview.html) for per-client instructions.

### Available Tools

The benchmark uses the SObject Reads server, which exposes these tools:

| Benchmark Task | MCP Tool | Example Args | Description |
|---|---|---|---|
| search | `find` | `{"q": "FIND {airbyte} IN ALL FIELDS RETURNING Account(Id, Name, Type, Industry LIMIT 10)"}` | SOSL search across objects |
| get | `soqlQuery` | `{"q": "SELECT Id, Name, Type, Industry FROM Account WHERE Id = '0015e00000FMsFhAAL'"}` | SOQL query for a single record |

The benchmark records these as `mcp__salesforce__find` and `mcp__salesforce__soqlQuery` in the recording files.

Notable behavior:

- The SObject Reads server is read-only. For write operations, use the SObject All or SObject Mutations servers instead.
- SOSL `FIND` queries search across all indexed fields. Results depend on the org's search index state.
- SOQL `SELECT` queries respect the org's field-level security and sharing rules.
- The server uses Streamable HTTP with session IDs. Each `initialize` handshake returns an `mcp-session-id` header that must be included in subsequent requests.
- Rate limits follow Salesforce's standard API limits for the org edition.

---

## Using These Servers With the Benchmark

### Viewing Results Without Recording

You do not need to install any third-party MCP server to view benchmark results. The committed `recording-stats.json` files contain aggregate metrics (token counts, record counts). Generate a comparison report with:

```bash
uv run agent-bench compare
```

To replay or validate recordings (which read the raw `recording.json` files), you must first record responses locally — raw recordings are gitignored and not committed.

### Capturing Fresh Recordings

The automated recorder script handles all native-mcp recordings. Set up your `.env` profile (see `.env.template`) and run:

```bash
uv run agent-bench record --path native-mcp --connectors linear,slack,zendesk,gong,salesforce --date 2026-04-30
```

This launches each connector's MCP server, executes the benchmark tool calls, and saves recordings in the standard format.

To record a single connector:

```bash
uv run agent-bench record --path native-mcp --connectors linear --date 2026-04-30
```

Stats are generated automatically after recording. To regenerate the comparison report:

```bash
uv run agent-bench compare --date 2026-04-30 --output artifacts/2026-04-30/comparison-report.md
```

To regenerate stats from existing recordings without re-recording:

```bash
uv run agent-bench record --path native-mcp --stats-only --date 2026-04-30
```

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

## Gong MCP

The benchmark uses the community **kenazk/gong-mcp** server (TypeScript, local Node.js process) via stdio transport.

**Repo:** https://github.com/kenazk/gong-mcp

### Prerequisites

- Node.js 18 or later
- A Gong API access key and secret (from Gong Settings > API)

### Environment Variables

Set these in your `.env` profile:

```bash
GONG_ACCESS_KEY=your-access-key
GONG_ACCESS_KEY_SECRET=your-access-secret
```

### How the Recording Script Launches It

The `GongMCP` class clones the repo, builds it, and runs the Node.js process:

```bash
node /home/ubuntu/gong-mcp/dist/index.js
```

The process reads JSON-RPC messages from stdin and writes responses to stdout. The access key and secret are passed via environment variables.

### Available Tools

| Benchmark Task | MCP Tool | Args | Description |
|---|---|---|---|
| get | `get_call` | `{"id": "1005803797056190704"}` | Retrieve a single call by ID |
| search | `list_calls` | `{"fromDateTime": "2025-01-01T00:00:00Z"}` | List calls from a given date |

Notable limitations:

- Gong's API has no keyword search. The `list_calls` tool lists calls by date range with a fixed page size of 100.
- No field selection; full call objects are always returned.
- This means the `gong-search` scenario is marked "Not Comparable" since it exercises fundamentally different operations between agent-mcp and native-mcp.

---

## Comparison With Agent MCP

| Dimension | Third-Party MCP | Agent MCP (`agent-mcp`) |
|---|---|---|
| Servers | One per service (Linear, Slack, Zendesk, Gong, Salesforce) | Unified `integrations_connectors_id_execute` |
| Auth | Per-service (OAuth, bot tokens, or API keys) | Single Airbyte Cloud OAuth credential set |
| Field selection | Not available; full responses returned | `select_fields` narrows returned fields |
| Response shape | Varies by provider (JSON, text, markdown) | Uniform typed JSON envelope |
| Hosting | Remote (Linear, Slack, Salesforce) or local (Zendesk, Gong) | Airbyte-hosted proxy at `mcp.airbyte.ai` |
