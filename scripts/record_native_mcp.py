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
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_ROOT = REPO_ROOT / "artifacts"


_DATE_OVERRIDE: str | None = None

def get_date_str() -> str:
    if _DATE_OVERRIDE:
        return _DATE_OVERRIDE
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

    # Search — use a broad query that returns results in this test workspace
    tool = "list_issues"
    args = {"query": "backend", "limit": 10}
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
    args = {"id": "AIR-55"}
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


# ---------- Gong MCP (stdio via kenazk/gong-mcp) ----------

GONG_MCP_SERVER_PATH = Path("/home/ubuntu/gong-mcp/dist/index.js")


class GongMCP:
    """Stdio-based MCP client for the kenazk/gong-mcp server."""

    def __init__(self, access_key: str, access_secret: str):
        env = os.environ.copy()
        env["GONG_ACCESS_KEY"] = access_key
        env["GONG_ACCESS_SECRET"] = access_secret
        self.proc = subprocess.Popen(
            ["node", str(GONG_MCP_SERVER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            env=env,
        )
        try:
            self._initialize()
        except Exception:
            self.proc.terminate()
            self.proc.wait(timeout=5)
            raise

    def _initialize(self):
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-bench-recorder", "version": "0.1"},
            },
        }
        self.proc.stdin.write(json.dumps(init_req) + "\n")
        self.proc.stdin.flush()
        self.proc.stdout.readline()  # consume init response
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        self.proc.stdin.write(json.dumps(notif) + "\n")
        self.proc.stdin.flush()

    def call_tool(self, tool_name: str, arguments: dict) -> tuple[dict | list | str, float]:
        req = {
            "jsonrpc": "2.0",
            "id": 2,
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


def record_gong(access_key: str, access_secret: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Gong native-mcp via the kenazk/gong-mcp MCP server."""
    results = []
    if dry_run:
        print("  [dry-run] Would record gong-list, gong-get, gong-search")
        return results

    mcp = GongMCP(access_key, access_secret)
    date = get_date_str()

    try:
        # List calls
        tool = "list_calls"
        args = {"fromDateTime": "2025-01-01T00:00:00Z"}
        response, wall_ms = mcp.call_tool(tool, args)
        path = save_recording("gong-list", [{
            "tool": f"mcp__gong__{tool}",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date)
        results.append(("gong-list", path))
        calls_list = response.get("calls", []) if isinstance(response, dict) else []
        print(f"    gong-list: {len(calls_list)} calls")

        # Get single call — the gong-mcp server has no get_call tool.
        # Use retrieve_transcripts with the target call ID as the closest
        # single-call retrieval available.
        call_id = "1005803797056190704"
        tool = "retrieve_transcripts"
        args = {"callIds": [call_id]}
        response, wall_ms = mcp.call_tool(tool, args)
        path = save_recording("gong-get", [{
            "tool": f"mcp__gong__{tool}",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date)
        results.append(("gong-get", path))
        print(f"    gong-get: {json.dumps(response)[:80]}...")

        # Search — the gong-mcp server has no search/keyword tool.
        # Use list_calls as a proxy (matches the agent-mcp approach of
        # listing then filtering client-side).
        tool = "list_calls"
        args = {"fromDateTime": "2025-01-01T00:00:00Z"}
        response, wall_ms = mcp.call_tool(tool, args)
        path = save_recording("gong-search", [{
            "tool": f"mcp__gong__{tool}",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date)
        results.append(("gong-search", path))
        print(f"    gong-search: {json.dumps(response)[:80]}...")
    finally:
        mcp.close()

    return results


# ---------- Salesforce API ----------

def get_salesforce_session_soap(
    username: str, password: str, security_token: str,
    instance_url: str = "https://airbyte.my.salesforce.com",
) -> tuple[str, str]:
    """Authenticate via SOAP login and return `(session_id, instance_url)`."""
    soap_body = (
        '<?xml version="1.0" encoding="utf-8" ?>'
        '<env:Envelope xmlns:xsd="http://www.w3.org/2001/XMLSchema"'
        '    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        '    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">'
        '  <env:Body>'
        '    <n1:login xmlns:n1="urn:partner.soap.sforce.com">'
        f'      <n1:username>{xml_escape(username)}</n1:username>'
        f'      <n1:password>{xml_escape(password)}{xml_escape(security_token)}</n1:password>'
        '    </n1:login>'
        '  </env:Body>'
        '</env:Envelope>'
    )
    r = requests.post(
        f"{instance_url}/services/Soap/u/59.0",
        headers={"Content-Type": "text/xml", "SOAPAction": "login"},
        data=soap_body,
        timeout=30,
    )
    r.raise_for_status()
    session_match = re.search(r"<sessionId>(.+?)</sessionId>", r.text)
    server_match = re.search(r"<serverUrl>(.+?)</serverUrl>", r.text)
    if not session_match or not server_match:
        raise RuntimeError(f"SOAP login failed: {r.text[:300]}")
    session_id = session_match.group(1)
    server_url = server_match.group(1)
    inst_match = re.search(r"(https://[^/]+)", server_url)
    resolved_instance = inst_match.group(1) if inst_match else instance_url
    return session_id, resolved_instance


def record_salesforce(
    username: str, password: str, security_token: str, dry_run: bool = False,
) -> list[tuple[str, Path]]:
    """Record Salesforce native responses via REST API (SOAP login)."""
    results = []
    if dry_run:
        print("  [dry-run] Would record salesforce-search, salesforce-get, salesforce-list")
        return results

    token, instance_url = get_salesforce_session_soap(username, password, security_token)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
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

    # Get (SOQL with field selection — returns only 4 fields, matching agent-mcp)
    account_id = "0015e00000FMsFhAAL"
    get_soql = f"SELECT Id, Name, Type, Industry FROM Account WHERE Id = '{account_id}'"
    start = time.time()
    r = requests.get(f"{base}/query/", headers=headers, params={"q": get_soql}, timeout=60)
    wall_ms = (time.time() - start) * 1000
    get_response = r.json()

    path = save_recording("salesforce-get", [{
        "tool": "mcp__salesforce__query",
        "args": {"q": get_soql},
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

def record_zendesk(subdomain: str, access_token: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Zendesk native responses via REST API (OAuth Bearer token)."""
    results = []
    if dry_run:
        print("  [dry-run] Would record zendesk-search, zendesk-get, zendesk-list")
        return results

    base = f"https://{subdomain}.zendesk.com/api/v2"
    headers = {"Authorization": f"Bearer {access_token}"}
    date = get_date_str()

    # Search
    start = time.time()
    r = requests.get(f"{base}/search.json", headers=headers, params={"query": "type:ticket sync", "per_page": 50}, timeout=60)
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

    # Get — use ticket ID 2 (known to exist in d3v-airbyte)
    ticket_id = "2"
    start = time.time()
    r = requests.get(f"{base}/tickets/{ticket_id}.json", headers=headers, timeout=60)
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
    r = requests.get(f"{base}/tickets.json", headers=headers, params={"per_page": 50, "sort_by": "created_at", "sort_order": "desc"}, timeout=60)
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
    parser.add_argument("--date", default=None,
                        help="Artifact date folder (YYYY-MM-DD). Defaults to today UTC.")
    parser.add_argument("--dry-run", action="store_true")
    opts = parser.parse_args()

    if opts.date:
        global _DATE_OVERRIDE
        _DATE_OVERRIDE = opts.date

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
                sf_user = os.environ.get("SALESFORCE_USERNAME", "marketing@airbyte.io")
                sf_pass = os.environ.get("SALESFORCE_PASSWORD", "")
                sf_token = os.environ.get("SALESFORCE_SECURITY_TOKEN", "")
                if not sf_pass or not sf_token:
                    sf_pass = load_secret("salesforce", "password", "prod-credentials-soap")
                    sf_token = load_secret("salesforce", "security_token", "prod-credentials-soap")
                if not sf_pass or not sf_token:
                    raise ValueError("Salesforce credentials missing: set SALESFORCE_PASSWORD and SALESFORCE_SECURITY_TOKEN env vars or populate 1Password prod-credentials-soap section.")
                all_results.extend(record_salesforce(sf_user, sf_pass, sf_token, opts.dry_run))

            elif connector == "zendesk":
                subdomain = load_secret("zendesk-support", "subdomain", "test-credentials-oauth")
                access_token = load_secret("zendesk-support", "access_token", "test-credentials-oauth")
                all_results.extend(record_zendesk(subdomain, access_token, opts.dry_run))

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
