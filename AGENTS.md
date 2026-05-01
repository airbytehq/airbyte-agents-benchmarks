# AGENTS.md

Standards and credential guidance for AI agents and human contributors working on the Airbyte Agents Benchmarks repo.

## Credential Sources for Devin Sessions

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

The `SONAR_CONNECTOR_CREDS_1PASS_TOKEN` secret provides `op` CLI access to the `direct-connector-credentials` vault, which contains third-party service credentials (Linear API keys, OAuth clients, etc.):

```bash
# List all items in the vault
OP_SERVICE_ACCOUNT_TOKEN="$SONAR_CONNECTOR_CREDS_1PASS_TOKEN" op item list \
  --vault="direct-connector-credentials" --format=json

# Get a specific connector's credentials (write to file to avoid exposing secrets in terminal)
OP_SERVICE_ACCOUNT_TOKEN="$SONAR_CONNECTOR_CREDS_1PASS_TOKEN" op item get linear \
  --vault="direct-connector-credentials" --format=json > /tmp/linear-creds.json

# Get a specific field value (write to file)
OP_SERVICE_ACCOUNT_TOKEN="$SONAR_CONNECTOR_CREDS_1PASS_TOKEN" op item get linear \
  --vault="direct-connector-credentials" --fields "label=api_key" --format=json > /tmp/linear-api-key.json
```

The vault structure uses items named after connectors (e.g., `linear`, `slack`), with sections prefixed `test-credentials-` (e.g., `test-credentials-api-key`, `test-credentials-oauth`).

**Note:** The `DEVIN_1PASSWORD_SERVICE_TOKEN` also provides access to the `direct-connector-credentials` vault. In future sessions, you can use either token:

```bash
# Using DEVIN_1PASSWORD_SERVICE_TOKEN (available by default in all Devin sessions)
OP_SERVICE_ACCOUNT_TOKEN="$DEVIN_1PASSWORD_SERVICE_TOKEN" op item list \
  --vault="direct-connector-credentials" --format=json
```

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

### `connector-credentials` CLI (human contributors)

The Sonar repo (`airbytehq/sonar`) includes a `connector-credentials` CLI for human contributors:

```bash
connector-credentials list              # List connectors with credentials
connector-credentials list linear       # List credential sets for linear
connector-credentials get linear oauth  # Get credentials in dotenv format
```

This CLI requires Python 3.13+ and is not currently usable in Devin sessions (which run Python 3.12 or 3.13 depending on the project).

## Recording Guidelines

### No PII in recordings

Recordings are committed to the repo and must not contain personally identifiable information. When choosing `select_fields` for a connector, exclude fields that return names, emails, or other PII. For example, prefer `state`, `team`, `labels` over `assignee` (which includes `name` and `email` sub-fields on Linear).

Before committing new recordings, verify with:

```bash
grep -rE '"email"|"phone"|"address"' artifacts/
```

If a field is needed for benchmark validity but contains PII, redact it to a placeholder (e.g., `user-1@example.com`) before committing.

## Existing Documentation

- [docs/REPRODUCTION.md](docs/REPRODUCTION.md) -- end-to-end guide for reproducing benchmark results
- [docs/THIRD_PARTY_MCP_SETUP.md](docs/THIRD_PARTY_MCP_SETUP.md) -- installation and configuration for Linear, Granola, and Slack MCP servers
- [docs/METHODOLOGY.md](docs/METHODOLOGY.md) -- measurement design, token counting, export gates
- [docs/RESULTS.md](docs/RESULTS.md) -- latest results pointer and known caveats
- [docs/BENEFITS.md](docs/BENEFITS.md) -- benefits narrative, token efficiency data, and claims guidance
