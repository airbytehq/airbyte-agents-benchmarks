"""Configuration — loads Airbyte creds + per-connector IDs from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


_ORG_VARS = {
    "AIRBYTE_ORGANIZATION_ID": "Airbyte organization UUID",
    "AIRBYTE_CLIENT_ID": "Airbyte application client ID",
    "AIRBYTE_CLIENT_SECRET": "Airbyte application client secret",
}


@dataclass
class LiveConfig:
    """Credentials + connector IDs for live benchmark runs."""

    organization_id: str
    client_id: str
    client_secret: str
    connector_ids: dict[str, str]  # {connector_name -> connector_id}

    @classmethod
    def from_env(cls, required_connectors: list[str] | None = None) -> "LiveConfig":
        """Load from environment. Raises with a clear message if anything is missing."""
        load_dotenv()

        missing: list[str] = []
        for var in _ORG_VARS:
            if not os.environ.get(var):
                missing.append(var)

        required_connectors = required_connectors or []
        connector_ids: dict[str, str] = {}
        for name in required_connectors:
            var = f"{name.upper()}_CONNECTOR_ID"
            value = os.environ.get(var)
            if not value:
                missing.append(var)
            else:
                connector_ids[name] = value

        if missing:
            lines = ["Missing environment variables:\n"]
            for var in missing:
                desc = _ORG_VARS.get(var, f"connector instance UUID for {var}")
                lines.append(f"  {var}  —  {desc}")
            lines.append("\nCopy .env.template to .env and fill in credentials, or run `agent-bench populate-env`.")
            raise EnvironmentError("\n".join(lines))

        return cls(
            organization_id=os.environ["AIRBYTE_ORGANIZATION_ID"],
            client_id=os.environ["AIRBYTE_CLIENT_ID"],
            client_secret=os.environ["AIRBYTE_CLIENT_SECRET"],
            connector_ids=connector_ids,
        )
