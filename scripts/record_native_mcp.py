"""Record native MCP responses from vendor MCP servers and APIs.

This script calls each vendor's native MCP server (or REST API where MCP
requires interactive OAuth) and saves recordings in the benchmark format:
  [{tool, args, wall_clock_ms, response}, ...]

Usage:
    # Record all connectors
    uv run python scripts/record_native_mcp.py

    # Record specific connectors
    uv run python scripts/record_native_mcp.py --connectors linear,slack

    # Dry run (show what would be recorded)
    uv run python scripts/record_native_mcp.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_ROOT = REPO_ROOT / "artifacts"


def get_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def save_recording(scenario: str, calls: list[dict], date: str | None = None) -> Path:
    date_str = date or get_date_str()
    out_path = ARTIFACTS_ROOT / date_str / f"{scenario}-scenario" / "native-mcp" / "recording.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(calls, indent=2))
    return out_path


# ---------- Linear MCP (Streamable HTTP) ----------

class LinearMCP:
    def __init__(self, api_key: str):
        self.url = "https://mcp.linear.app/mcp"
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {api_key}",
        }
        self.session_id: str | None = None
        self._initialize()

    def _initialize(self):
        init_req = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-bench-recorder", "version": "0.1"},
            },
        }
        r = requests.post(self.url, json=init_req, headers=self.headers, timeout=30)
        r.raise_for_status()
        self.session_id = r.headers.get("mcp-session-id", "")
        self.headers["mcp-session-id"] = self.session_id
        # Send initialized notification
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        requests.post(self.url, json=notif, headers=self.headers, timeout=30)

    def call_tool(self, tool_name: str, arguments: dict) -> tuple[dict, float]:
        req = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        start = time.time()
        r = requests.post(self.url, json=req, headers=self.headers, timeout=60)
        wall_ms = (time.time() - start) * 1000

        for line in r.text.split("\n"):
            if line.startswith("data:"):
                data = json.loads(line[5:].strip())
                result = data.get("result", {})
                content = result.get("content", [])
                if content:
                    text = content[0].get("text", "")
                    try:
                        return json.loads(text), wall_ms
                    except json.JSONDecodeError:
                        return {"text": text}, wall_ms
                error = data.get("error")
                if error:
                    return {"error": error}, wall_ms
        return {"error": "no response"}, wall_ms


def record_linear(api_key: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Linear native-mcp for search, get, list scenarios."""
    results = []
    if dry_run:
        print("  [dry-run] Would record linear-search, linear-get, linear-list")
        return results

    mcp = LinearMCP(api_key)
    date = get_date_str()

    # Search
    tool = "list_issues"
    args = {"query": "context store", "limit": 10}
    response, wall_ms = mcp.call_tool(tool, args)
    path = save_recording("linear-search", [{
        "tool": f"mcp__claude_ai_Linear__{tool}",
        "args": args,
        "wall_clock_ms": round(wall_ms, 1),
        "response": response,
    }], date)
    results.append(("linear-search", path))
    print(f"    linear-search: {json.dumps(response)[:80]}...")

    # Get
    tool = "get_issue"
    args = {"id": "AGENTIC-338"}
    response, wall_ms = mcp.call_tool(tool, args)
    path = save_recording("linear-get", [{
        "tool": f"mcp__claude_ai_Linear__{tool}",
        "args": args,
        "wall_clock_ms": round(wall_ms, 1),
        "response": response,
    }], date)
    results.append(("linear-get", path))
    print(f"    linear-get: {json.dumps(response)[:80]}...")

    # List
    tool = "list_issues"
    args = {"limit": 50}
    response, wall_ms = mcp.call_tool(tool, args)
    path = save_recording("linear-list", [{
        "tool": f"mcp__claude_ai_Linear__{tool}",
        "args": args,
        "wall_clock_ms": round(wall_ms, 1),
        "response": response,
    }], date)
    results.append(("linear-list", path))
    issues = response.get("issues", [])
    print(f"    linear-list: {len(issues)} issues")

    return results


# ---------- Slack MCP (stdio via npx) ----------

class SlackMCP:
    def __init__(self, bot_token: str, team_id: str):
        env = os.environ.copy()
        env["SLACK_BOT_TOKEN"] = bot_token
        env["SLACK_TEAM_ID"] = team_id
        self.proc = subprocess.Popen(
            ["npx", "-y", "@modelcontextprotocol/server-slack"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
        self._initialize()

    def _initialize(self):
        init_req = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-bench-recorder", "version": "0.1"},
            },
        }
        self.proc.stdin.write(json.dumps(init_req) + "\n")
        self.proc.stdin.flush()
        self.proc.stdout.readline()  # consume init response
        # Send initialized notification (required by MCP protocol)
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        self.proc.stdin.write(json.dumps(notif) + "\n")
        self.proc.stdin.flush()

    def call_tool(self, tool_name: str, arguments: dict) -> tuple[dict | list | str, float]:
        req = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        start = time.time()
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        resp_line = self.proc.stdout.readline()
        wall_ms = (time.time() - start) * 1000

        data = json.loads(resp_line)
        result = data.get("result", {})
        content = result.get("content", [])
        if content:
            text = content[0].get("text", "")
            try:
                return json.loads(text), wall_ms
            except json.JSONDecodeError:
                return {"text": text}, wall_ms
        return {"error": "no content"}, wall_ms

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)


def record_slack(bot_token: str, team_id: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Slack native-mcp for search, get, list scenarios."""
    results = []
    if dry_run:
        print("  [dry-run] Would record slack-search, slack-get, slack-list")
        return results

    mcp = SlackMCP(bot_token, team_id)
    date = get_date_str()

    try:
        # Search
        tool = "slack_list_channels"
        args = {"limit": 20}
        response, wall_ms = mcp.call_tool(tool, args)
        # The benchmark uses slack_search_channels tool name but actual MCP exposes slack_list_channels
        path = save_recording("slack-search", [{
            "tool": "mcp__claude_ai_Slack__slack_list_channels",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date)
        results.append(("slack-search", path))
        channels = response.get("channels", []) if isinstance(response, dict) else []
        print(f"    slack-search: {len(channels)} channels")

        # Get (search-then-filter since no get-by-ID)
        tool = "slack_list_channels"
        args = {"limit": 20}
        response, wall_ms = mcp.call_tool(tool, args)
        path = save_recording("slack-get", [{
            "tool": "mcp__claude_ai_Slack__slack_list_channels",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date)
        results.append(("slack-get", path))
        print(f"    slack-get: {json.dumps(response)[:80]}...")

        # List (3 pages of 20)
        calls = []
        for page in range(3):
            page_args = {"limit": 20}
            response, wall_ms = mcp.call_tool("slack_list_channels", page_args)
            calls.append({
                "tool": "mcp__claude_ai_Slack__slack_list_channels",
                "args": page_args,
                "wall_clock_ms": round(wall_ms, 1),
                "response": response,
            })
        path = save_recording("slack-list", calls, date)
        results.append(("slack-list", path))
        print(f"    slack-list: {len(calls)} calls")
    finally:
        mcp.close()

    return results


# ---------- Gong API ----------

def record_gong(access_key: str, access_secret: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Gong native responses via REST API."""
    results = []
    if dry_run:
        print("  [dry-run] Would record gong-search, gong-get, gong-list")
        return results

    auth = base64.b64encode(f"{access_key}:{access_secret}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    base_url = "https://api.gong.io/v2"
    date = get_date_str()

    # List calls (used for both list and to find a call for get)
    start = time.time()
    r = requests.get(f"{base_url}/calls", headers=headers, params={"fromDateTime": "2025-01-01T00:00:00Z"}, timeout=60)
    wall_ms = (time.time() - start) * 1000
    list_response = r.json()

    path = save_recording("gong-list", [{
        "tool": "mcp__gong__list_calls",
        "args": {"fromDateTime": "2025-01-01T00:00:00Z"},
        "wall_clock_ms": round(wall_ms, 1),
        "response": list_response,
    }], date)
    results.append(("gong-list", path))
    calls_list = list_response.get("calls", [])
    print(f"    gong-list: {len(calls_list)} calls")

    # Get single call
    call_id = "1005803797056190704"
    start = time.time()
    r = requests.get(f"{base_url}/calls/{call_id}", headers=headers, timeout=60)
    wall_ms = (time.time() - start) * 1000
    get_response = r.json()

    path = save_recording("gong-get", [{
        "tool": "mcp__gong__get_call",
        "args": {"id": call_id},
        "wall_clock_ms": round(wall_ms, 1),
        "response": get_response,
    }], date)
    results.append(("gong-get", path))
    print(f"    gong-get: {json.dumps(get_response)[:80]}...")

    # Search - Gong doesn't have keyword search on calls via REST easily,
    # use the list endpoint filtered as a search proxy
    start = time.time()
    r = requests.post(f"{base_url}/calls/extensive", headers=headers, timeout=60,
                      json={"filter": {"fromDateTime": "2025-01-01T00:00:00Z"}, "contentSelector": {"exposedFields": {"call": ["title", "scheduled", "duration", "id"]}}})
    wall_ms = (time.time() - start) * 1000
    search_response = r.json()

    path = save_recording("gong-search", [{
        "tool": "mcp__gong__search_calls",
        "args": {"keyword": "airbyte"},
        "wall_clock_ms": round(wall_ms, 1),
        "response": search_response,
    }], date)
    results.append(("gong-search", path))
    print(f"    gong-search: {json.dumps(search_response)[:80]}...")

    return results


# ---------- Salesforce API ----------

def get_salesforce_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Exchange refresh token for access token."""
    r = requests.post("https://login.salesforce.com/services/oauth2/token", timeout=30, data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    })
    r.raise_for_status()
    return r.json()["access_token"]


def record_salesforce(client_id: str, client_secret: str, refresh_token: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Salesforce native responses via REST API."""
    results = []
    if dry_run:
        print("  [dry-run] Would record salesforce-search, salesforce-get, salesforce-list")
        return results

    token = get_salesforce_token(client_id, client_secret, refresh_token)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # Need to get instance URL
    r = requests.get("https://login.salesforce.com/services/oauth2/userinfo", headers=headers, timeout=30)
    # Fall back to standard instance
    instance_url = "https://airbyte-dev-ed.develop.my.salesforce.com"
    if r.ok:
        profile = r.json()
        # Try to extract org URL
        urls = profile.get("urls", {})
        if "custom_domain" in urls:
            instance_url = urls["custom_domain"].rstrip("/")
    
    base = f"{instance_url}/services/data/v59.0"
    date = get_date_str()

    # Search (SOSL)
    sosl = "FIND {airbyte} IN ALL FIELDS RETURNING Account(Id, Name, Type, Industry)"
    start = time.time()
    r = requests.get(f"{base}/search/", headers=headers, params={"q": sosl}, timeout=60)
    wall_ms = (time.time() - start) * 1000
    search_response = r.json()

    path = save_recording("salesforce-search", [{
        "tool": "mcp__salesforce__search",
        "args": {"query": "airbyte"},
        "wall_clock_ms": round(wall_ms, 1),
        "response": search_response,
    }], date)
    results.append(("salesforce-search", path))
    records = search_response.get("searchRecords", []) if isinstance(search_response, dict) else []
    print(f"    salesforce-search: {len(records)} records")

    # Get
    account_id = "0015e00000FMsFhAAL"
    start = time.time()
    r = requests.get(f"{base}/sobjects/Account/{account_id}", headers=headers, timeout=60)
    wall_ms = (time.time() - start) * 1000
    get_response = r.json()

    path = save_recording("salesforce-get", [{
        "tool": "mcp__salesforce__get_record",
        "args": {"sobject": "Account", "id": account_id},
        "wall_clock_ms": round(wall_ms, 1),
        "response": get_response,
    }], date)
    results.append(("salesforce-get", path))
    print(f"    salesforce-get: {len(json.dumps(get_response))} bytes")

    # List (SOQL)
    soql = "SELECT Id, Name, Type, Industry FROM Account LIMIT 50"
    start = time.time()
    r = requests.get(f"{base}/query/", headers=headers, params={"q": soql}, timeout=60)
    wall_ms = (time.time() - start) * 1000
    list_response = r.json()

    path = save_recording("salesforce-list", [{
        "tool": "mcp__salesforce__query",
        "args": {"q": soql},
        "wall_clock_ms": round(wall_ms, 1),
        "response": list_response,
    }], date)
    results.append(("salesforce-list", path))
    records = list_response.get("records", []) if isinstance(list_response, dict) else []
    print(f"    salesforce-list: {len(records)} records")

    return results


# ---------- Zendesk API ----------

def record_zendesk(subdomain: str, email: str, api_token: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Zendesk native responses via REST API."""
    results = []
    if dry_run:
        print("  [dry-run] Would record zendesk-search, zendesk-get, zendesk-list")
        return results

    base = f"https://{subdomain}.zendesk.com/api/v2"
    auth = (f"{email}/token", api_token)
    date = get_date_str()

    # Search
    start = time.time()
    r = requests.get(f"{base}/search.json", auth=auth, params={"query": "type:ticket sync", "per_page": 50}, timeout=60)
    wall_ms = (time.time() - start) * 1000
    search_response = r.json()

    path = save_recording("zendesk-search", [{
        "tool": "mcp__zendesk__search_tickets",
        "args": {"query": "sync"},
        "wall_clock_ms": round(wall_ms, 1),
        "response": search_response,
    }], date)
    results.append(("zendesk-search", path))
    ticket_results = search_response.get("results", []) if isinstance(search_response, dict) else []
    print(f"    zendesk-search: {len(ticket_results)} results")

    # Get
    ticket_id = "6885"
    start = time.time()
    r = requests.get(f"{base}/tickets/{ticket_id}.json", auth=auth, timeout=60)
    wall_ms = (time.time() - start) * 1000
    get_response = r.json()

    path = save_recording("zendesk-get", [{
        "tool": "mcp__zendesk__get_ticket",
        "args": {"id": ticket_id},
        "wall_clock_ms": round(wall_ms, 1),
        "response": get_response,
    }], date)
    results.append(("zendesk-get", path))
    print(f"    zendesk-get: {len(json.dumps(get_response))} bytes")

    # List
    start = time.time()
    r = requests.get(f"{base}/tickets.json", auth=auth, params={"per_page": 50, "sort_by": "created_at", "sort_order": "desc"}, timeout=60)
    wall_ms = (time.time() - start) * 1000
    list_response = r.json()

    path = save_recording("zendesk-list", [{
        "tool": "mcp__zendesk__list_tickets",
        "args": {"limit": 50},
        "wall_clock_ms": round(wall_ms, 1),
        "response": list_response,
    }], date)
    results.append(("zendesk-list", path))
    tickets = list_response.get("tickets", []) if isinstance(list_response, dict) else []
    print(f"    zendesk-list: {len(tickets)} tickets")

    return results


# ---------- Main ----------

def load_secret(item: str, field: str, section: str | None = None) -> str:
    """Load a secret from 1Password vault."""
    token = os.environ.get("DEVIN_1PASSWORD_SERVICE_TOKEN") or os.environ.get("SONAR_CONNECTOR_CREDS_1PASS_TOKEN", "")
    env = os.environ.copy()
    env["OP_SERVICE_ACCOUNT_TOKEN"] = token

    cmd = ["op", "item", "get", item, "--vault=direct-connector-credentials", "--format=json", "--reveal"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    data = json.loads(result.stdout)

    for f in data.get("fields", []):
        f_section = f.get("section", {}).get("label", "")
        f_label = f.get("label", "")
        if f_label == field:
            if section is None or f_section == section:
                return f.get("value", "")
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Record native MCP responses")
    parser.add_argument("--connectors", default="linear,slack,gong,salesforce,zendesk",
                        help="Comma-separated list of connectors to record")
    parser.add_argument("--dry-run", action="store_true")
    opts = parser.parse_args()

    connectors = [c.strip() for c in opts.connectors.split(",")]
    all_results = []

    for connector in connectors:
        print(f"\n{'='*40}")
        print(f"Recording: {connector}")
        print(f"{'='*40}")

        try:
            if connector == "linear":
                api_key = load_secret("linear", "api_key", "test-credentials-api-key")
                all_results.extend(record_linear(api_key, opts.dry_run))

            elif connector == "slack":
                bot_token = load_secret("slack", "bot_key", "test-credentials-bot")
                team_id = "T02TET08MDH"
                all_results.extend(record_slack(bot_token, team_id, opts.dry_run))

            elif connector == "gong":
                access_key = load_secret("gong", "access_key", "test-credentials-basic")
                access_secret = load_secret("gong", "access_key_secret", "test-credentials-basic")
                all_results.extend(record_gong(access_key, access_secret, opts.dry_run))

            elif connector == "salesforce":
                client_id = load_secret("salesforce", "client_id", "test-credentials-oauth")
                client_secret = load_secret("salesforce", "client_secret", "test-credentials-oauth")
                refresh_token = load_secret("salesforce", "refresh_token", "test-credentials-oauth")
                all_results.extend(record_salesforce(client_id, client_secret, refresh_token, opts.dry_run))

            elif connector == "zendesk":
                subdomain = load_secret("zendesk-support", "subdomain", "test-credentials-basic")
                email = load_secret("zendesk-support", "email", "test-credentials-basic")
                api_token = load_secret("zendesk-support", "api_token", "test-credentials-basic")
                all_results.extend(record_zendesk(subdomain, email, api_token, opts.dry_run))

            else:
                print(f"  Unknown connector: {connector}")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*40}")
    print(f"Done. Recorded {len(all_results)} scenarios.")
    for scenario, path in all_results:
        print(f"  {scenario} → {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
