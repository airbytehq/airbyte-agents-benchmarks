"""Populate `.env` files from 1Password.

Reads the `.env.template` to discover which variables are declared, fetches
native-MCP connector credentials from the `direct-connector-credentials`
vault, and writes a ready-to-use `.env` file. Agent-MCP variables
(`AIRBYTE_ORGANIZATION_ID`, connector IDs, etc.) are left as-is if already
present in the output file, or blank for the user to fill in.

The recording layer (`native_mcp_recorder`, `agent_mcp_recorder`) never
touches 1Password directly — it reads `.env` only.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_TEMPLATE = REPO_ROOT / ".env.template"
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

VAULT = "direct-connector-credentials"

# Mapping from env var name → (1Password item, field, section).
# Only native-MCP credentials that live in 1Password are listed here.
_OP_FIELD_MAP: dict[str, tuple[str, str, str]] = {
    "LINEAR_API_KEY": ("linear", "api_key", "test-credentials-api-key"),
    "SLACK_USER_OAUTH_TOKEN": ("slack", "user_oauth_token", "test-credentials-mcp"),
    "GONG_ACCESS_KEY": ("gong", "access_key", "test-credentials-basic"),
    "GONG_ACCESS_KEY_SECRET": ("gong", "access_key_secret", "test-credentials-basic"),
    "SF_MCP_CONSUMER_KEY": ("salesforce", "consumer_key", "test-credentials-mcp"),
    "SF_MCP_CONSUMER_SECRET": ("salesforce", "consumer_secret", "test-credentials-mcp"),
    "SF_MCP_REFRESH_TOKEN": ("salesforce", "refresh_token", "test-credentials-mcp"),
    "ZENDESK_SUBDOMAIN": ("zendesk-support", "subdomain", "test-credentials-oauth"),
    "ZENDESK_ACCESS_TOKEN": ("zendesk-support", "access_token", "test-credentials-oauth"),
}


def _resolve_op_token() -> str:
    """Return a 1Password service account token from the environment."""
    token = os.environ.get("SONAR_CONNECTOR_CREDS_1PASS_TOKEN") or os.environ.get(
        "DEVIN_1PASSWORD_SERVICE_TOKEN", ""
    )
    if not token:
        raise EnvironmentError(
            "No 1Password token found. Set SONAR_CONNECTOR_CREDS_1PASS_TOKEN or "
            "DEVIN_1PASSWORD_SERVICE_TOKEN."
        )
    return token


def _fetch_op_item(item: str, op_token: str, cache: dict[str, list[dict]]) -> list[dict]:
    """Fetch and cache a 1Password item's fields list.

    Returns the `fields` list from the item JSON. Subsequent calls for the
    same item name reuse the cached result.
    """
    if item in cache:
        return cache[item]

    env = os.environ.copy()
    env["OP_SERVICE_ACCOUNT_TOKEN"] = op_token

    cmd = [
        "op", "item", "get", item,
        f"--vault={VAULT}",
        "--format=json",
        "--reveal",
    ]
    print(f"  Fetching {item} from 1Password ...")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"`op item get {item}` failed: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    fields = data.get("fields", [])
    cache[item] = fields
    return fields


def _extract_field(fields: list[dict], field: str, section: str) -> str:
    """Extract a field value from a cached 1Password fields list."""
    for f_entry in fields:
        f_section = (f_entry.get("section") or {}).get("label", "")
        f_label = f_entry.get("label", "")
        if f_label == field and f_section == section:
            return f_entry.get("value", "")
    return ""


def _parse_template(template_path: Path = ENV_TEMPLATE) -> list[str]:
    """Return the ordered list of env var names declared in `.env.template`."""
    names: list[str] = []
    for line in template_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            names.append(key)
    return names


def _read_existing_env(env_path: Path) -> dict[str, str]:
    """Read an existing `.env` file into a dict, preserving decoded values.

    Uses python-dotenv's parser to ensure correct unescaping (e.g. `\\$` → `$`)
    so that re-writing through `_quote_value` doesn't double-escape.
    """
    from dotenv import dotenv_values

    if not env_path.is_file():
        return {}
    raw = dotenv_values(env_path)
    return {k: v for k, v in raw.items() if v is not None}


def _quote_value(value: str) -> str:
    """Wrap a value in quotes if it contains dotenv-sensitive chars."""
    if not value:
        return ""
    # Escape $ as \$ inside double quotes to prevent python-dotenv interpolation
    if "$" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\n", "\\n")
        return f'"{escaped}"'
    needs_quoting = any(c in value for c in (" ", "#", "'", '"', "\n", "\t"))
    if needs_quoting:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return value


def populate_env(
    output_path: Path = DEFAULT_ENV_PATH,
    overwrite: bool = False,
) -> Path:
    """Fetch native-MCP credentials from 1Password and write a `.env` file.

    Variables already set in an existing `.env` are preserved unless
    `overwrite` is True. Agent-MCP variables not in 1Password are left
    blank for manual entry.

    Returns the path to the written file.
    """
    op_token = _resolve_op_token()
    template_vars = _parse_template()
    existing = {} if overwrite else _read_existing_env(output_path)

    lines = [
        "# Auto-generated by `agent-bench populate-env`.",
        "# Edit freely — this file is gitignored.",
        "",
    ]

    item_cache: dict[str, list[dict]] = {}

    for var in template_vars:
        # Keep existing value if present
        if var in existing and existing[var]:
            lines.append(f"{var}={_quote_value(existing[var])}")
            continue

        # Try 1Password lookup
        if var in _OP_FIELD_MAP:
            item, field, section = _OP_FIELD_MAP[var]
            fields = _fetch_op_item(item, op_token, item_cache)
            value = _extract_field(fields, field, section)
            if value:
                lines.append(f"{var}={_quote_value(value)}")
                print(f"  {var} ✓")
                continue

        # Not in 1Password or not found — leave blank
        lines.append(f"{var}=")

    output_path.write_text("\n".join(lines) + "\n")
    return output_path
