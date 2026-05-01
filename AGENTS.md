# AGENTS.md

Standards and credential guidance for AI agents and human contributors working on the Airbyte Agents Benchmarks repo.

## Credential Management

All credentials are loaded from environment variables via `.env` files. The recording
layer never touches 1Password or other secret stores directly.

### Quick start

```bash
# Copy template and fill in Agent MCP values manually:
cp .env.template .env

# Auto-populate native-MCP secrets from 1Password:
uv run agent-bench populate-env
```

### Profiles

To switch between orgs or credential sets, maintain multiple `.env` files
(e.g., `.env.prod`, `.env.staging`) and copy the active one to `.env`.
All `.env*` files except `.env.template` are gitignored.

### Benchmark testing organization

The benchmarks run against this org: [145bfc59-1eed-4266-96bf-d527fb3e5765](https://app.airbyte.ai/organizations/145bfc59-1eed-4266-96bf-d527fb3e5765/connectors)

### Finding workspaces and sources programmatically

```
# List workspaces for an org
sonar-operator-mcp call: action=list, entity=workspaces, organization_id=<org-id>

# List sources in a workspace
sonar-operator-mcp call: action=list, entity=sources, organization_id=<org-id>, args={workspace_id: <ws-id>}
```

### 1Password (`direct-connector-credentials` vault)

The `populate-env` command uses `SONAR_CONNECTOR_CREDS_1PASS_TOKEN` (or
`DEVIN_1PASSWORD_SERVICE_TOKEN`) to fetch native-MCP secrets from the
`direct-connector-credentials` vault. You can also query the vault
manually:

```bash
OP_SERVICE_ACCOUNT_TOKEN="$SONAR_CONNECTOR_CREDS_1PASS_TOKEN" op item list \
  --vault="direct-connector-credentials" --format=json
```

The vault structure uses items named after connectors (e.g., `linear`, `slack`), with sections prefixed `test-credentials-` (e.g., `test-credentials-api-key`, `test-credentials-oauth`).

### GCP Secret Manager (PyAirbyte)

Airbyte CI stores integration test credentials in Google Cloud Secret Manager (project: `dataline-integration-testing`). PyAirbyte provides direct access via `GCP_GSM_CREDENTIALS`:

```python
import os
from airbyte.secrets.google_gsm import GoogleGSMSecretManager

secret_mgr = GoogleGSMSecretManager(
    project="dataline-integration-testing",
    credentials_json=os.environ.get("GCP_GSM_CREDENTIALS"),
)

# Search by connector label
secrets = list(secret_mgr.fetch_secrets(filter_string="labels.connector:source-slack"))
for s in secrets:
    config = s.parse_json()
    print(config)
```

**Current GSM coverage:** Slack credentials are available. Linear and Granola are not currently in GSM.

## Salesforce Native MCP — Token Refresh

The Salesforce hosted MCP endpoint (`api.salesforce.com/platform/mcp`) requires an access token from a **production** Salesforce org — Developer Edition orgs (e.g., `airbyte-dev-ed`) will return 401.

**Key facts:**
- Org domain: `airbyte.my.salesforce.com` (never use `login.salesforce.com`)
- The External Client App ("Salesforce MCP (Internal Access)") requires **PKCE** for OAuth flows
- Callback URL: `https://claude.ai/api/mcp/auth_callback` (must match exactly)
- Do **not** pass explicit `scope` parameters — the app's pre-configured scopes (`refresh_token mcp_api`) apply automatically
- See [docs/THIRD_PARTY_MCP_SETUP.md](docs/THIRD_PARTY_MCP_SETUP.md#obtaining-a-refresh-token) for the full step-by-step OAuth flow

## Recording Guidelines

### No PII in committed files

Raw recording JSON files (`recording.json`) are gitignored and never committed. Only `recording-stats.json` files (which contain aggregate metrics, not record-level data) are committed.

Since recordings stay local, `select_fields` may include name fields when needed for benchmark validity (e.g., searching users by `name`). However, avoid including email addresses, phone numbers, or other contact information in `select_fields` when not required by the scenario.

## Existing Documentation

- [docs/REPRODUCTION.md](docs/REPRODUCTION.md) -- end-to-end guide for reproducing benchmark results
- [docs/THIRD_PARTY_MCP_SETUP.md](docs/THIRD_PARTY_MCP_SETUP.md) -- installation and configuration for native MCP servers (Linear, Slack, Gong, Salesforce, Zendesk)
- [docs/METHODOLOGY.md](docs/METHODOLOGY.md) -- measurement design, token counting, export gates
- [docs/RESULTS.md](docs/RESULTS.md) -- latest results pointer and known caveats
- [docs/BENEFITS.md](docs/BENEFITS.md) -- benefits narrative, token efficiency data, and claims guidance
