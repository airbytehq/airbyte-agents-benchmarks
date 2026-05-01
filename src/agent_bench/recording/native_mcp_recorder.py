"""Record native MCP responses from vendor MCP servers and APIs.

Calls each vendor's native MCP server (or REST API where MCP requires
interactive OAuth) and saves recordings in the benchmark format:
`[{tool, args, wall_clock_ms, response}, ...]`
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

from agent_bench.recording.common import (
    default_date,
    load_secret,
    save_recording,
)


# ---------------------------------------------------------------------------
# Linear MCP (Streamable HTTP)
# ---------------------------------------------------------------------------


class LinearMCP:
    """Streamable HTTP client for Linear's hosted MCP server."""

    def __init__(self, api_key: str) -> None:
        self.url = "https://mcp.linear.app/mcp"
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {api_key}",
        }
        self.session_id: str | None = None
        self._initialize()

    def _initialize(self) -> None:
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


def record_linear(api_key: str, date: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Linear native-mcp for search, get, project-list, user-list scenarios."""
    results: list[tuple[str, Path]] = []
    if dry_run:
        print("  [dry-run] Would record linear-search, linear-get, linear-project-list, linear-user-list")
        return results

    mcp = LinearMCP(api_key)

    # Search
    tool = "list_issues"
    args = {"query": "backend", "limit": 10}
    response, wall_ms = mcp.call_tool(tool, args)
    path = save_recording("linear-search", [{
        "tool": f"mcp__claude_ai_Linear__{tool}",
        "args": args,
        "wall_clock_ms": round(wall_ms, 1),
        "response": response,
    }], date, "native-mcp")
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
    }], date, "native-mcp")
    results.append(("linear-get", path))
    print(f"    linear-get: {json.dumps(response)[:80]}...")

    # Project list (list all projects)
    tool = "list_projects"
    args = {}
    response, wall_ms = mcp.call_tool(tool, args)
    path = save_recording("linear-project-list", [{
        "tool": f"mcp__claude_ai_Linear__{tool}",
        "args": args,
        "wall_clock_ms": round(wall_ms, 1),
        "response": response,
    }], date, "native-mcp")
    results.append(("linear-project-list", path))
    projects = response.get("projects", response.get("nodes", []))
    if isinstance(projects, list):
        print(f"    linear-project-list: {len(projects)} projects")
    else:
        print(f"    linear-project-list: {json.dumps(response)[:80]}...")

    # User list (list all users)
    tool = "list_users"
    args = {}
    response, wall_ms = mcp.call_tool(tool, args)
    path = save_recording("linear-user-list", [{
        "tool": f"mcp__claude_ai_Linear__{tool}",
        "args": args,
        "wall_clock_ms": round(wall_ms, 1),
        "response": response,
    }], date, "native-mcp")
    results.append(("linear-user-list", path))
    users = response.get("users", response.get("nodes", []))
    if isinstance(users, list):
        print(f"    linear-user-list: {len(users)} users")
    else:
        print(f"    linear-user-list: {json.dumps(response)[:80]}...")

    return results


# ---------------------------------------------------------------------------
# Slack MCP (stdio via npx)
# ---------------------------------------------------------------------------


class SlackMCP:
    """Stdio-based MCP client for the Slack MCP server (`npx`)."""

    def __init__(self, bot_token: str, team_id: str) -> None:
        env = os.environ.copy()
        env["SLACK_BOT_TOKEN"] = bot_token
        env["SLACK_TEAM_ID"] = team_id
        self.proc = subprocess.Popen(  # noqa: S603, S607
            ["npx", "-y", "@modelcontextprotocol/server-slack"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
        self._initialize()

    def _initialize(self) -> None:
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

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=5)


def record_slack(bot_token: str, team_id: str, date: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Slack native-mcp for search, get, list-all, and user-list scenarios."""
    results: list[tuple[str, Path]] = []
    if dry_run:
        print("  [dry-run] Would record slack-search, slack-get, slack-list-all, slack-user-list")
        return results

    mcp = SlackMCP(bot_token, team_id)

    try:
        # Search
        tool = "slack_list_channels"
        args = {"limit": 20}
        response, wall_ms = mcp.call_tool(tool, args)
        path = save_recording("slack-search", [{
            "tool": "mcp__claude_ai_Slack__slack_list_channels",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date, "native-mcp")
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
        }], date, "native-mcp")
        results.append(("slack-get", path))
        print(f"    slack-get: {json.dumps(response)[:80]}...")

        # List-all — paginate all channels (100 per page until exhausted)
        calls: list[dict] = []
        page_args: dict = {"limit": 100}
        while True:
            response, wall_ms = mcp.call_tool("slack_list_channels", page_args)
            calls.append({
                "tool": "mcp__claude_ai_Slack__slack_list_channels",
                "args": page_args,
                "wall_clock_ms": round(wall_ms, 1),
                "response": response,
            })
            metadata = response.get("response_metadata", {}) if isinstance(response, dict) else {}
            next_cursor = metadata.get("next_cursor", "")
            if not next_cursor:
                break
            page_args = {"limit": 100, "cursor": next_cursor}
        path = save_recording("slack-list-all", calls, date, "native-mcp")
        results.append(("slack-list-all", path))
        total_channels = sum(
            len(c["response"].get("channels", []))
            for c in calls if isinstance(c.get("response"), dict)
        )
        print(f"    slack-list-all: {total_channels} channels across {len(calls)} calls")

        # User list — paginate all users (200 per page until exhausted)
        user_calls = []
        page_args = {"limit": 200}
        while True:
            response, wall_ms = mcp.call_tool("slack_get_users", page_args)
            user_calls.append({
                "tool": "mcp__claude_ai_Slack__slack_get_users",
                "args": page_args,
                "wall_clock_ms": round(wall_ms, 1),
                "response": response,
            })
            metadata = response.get("response_metadata", {}) if isinstance(response, dict) else {}
            next_cursor = metadata.get("next_cursor", "")
            if not next_cursor:
                break
            page_args = {"limit": 200, "cursor": next_cursor}
        path = save_recording("slack-user-list", user_calls, date, "native-mcp")
        results.append(("slack-user-list", path))
        total_members = sum(
            len(c["response"].get("members", []))
            for c in user_calls if isinstance(c.get("response"), dict)
        )
        print(f"    slack-user-list: {total_members} members across {len(user_calls)} calls")
    finally:
        mcp.close()

    return results


# ---------------------------------------------------------------------------
# Gong MCP (stdio via kenazk/gong-mcp)
# ---------------------------------------------------------------------------

GONG_MCP_SERVER_PATH = Path("/home/ubuntu/gong-mcp/dist/index.js")


class GongMCP:
    """Stdio-based MCP client for the `kenazk/gong-mcp` server."""

    def __init__(self, access_key: str, access_secret: str) -> None:
        env = os.environ.copy()
        env["GONG_ACCESS_KEY"] = access_key
        env["GONG_ACCESS_SECRET"] = access_secret
        self.proc = subprocess.Popen(  # noqa: S603, S607
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

    def _initialize(self) -> None:
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

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=5)


def record_gong(access_key: str, access_secret: str, date: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Gong native-mcp via the `kenazk/gong-mcp` MCP server."""
    results: list[tuple[str, Path]] = []
    if dry_run:
        print("  [dry-run] Would record gong-get, gong-search")
        return results

    mcp = GongMCP(access_key, access_secret)

    try:
        # Get single call metadata by ID
        call_id = "1005803797056190704"
        tool = "get_call"
        args = {"id": call_id}
        response, wall_ms = mcp.call_tool(tool, args)
        path = save_recording("gong-get", [{
            "tool": f"mcp__gong__{tool}",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date, "native-mcp")
        results.append(("gong-get", path))
        print(f"    gong-get: {json.dumps(response)[:80]}...")

        # Search
        tool = "list_calls"
        args = {"fromDateTime": "2025-01-01T00:00:00Z"}
        response, wall_ms = mcp.call_tool(tool, args)
        path = save_recording("gong-search", [{
            "tool": f"mcp__gong__{tool}",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date, "native-mcp")
        results.append(("gong-search", path))
        print(f"    gong-search: {json.dumps(response)[:80]}...")
    finally:
        mcp.close()

    return results


# ---------------------------------------------------------------------------
# Salesforce Hosted MCP
# ---------------------------------------------------------------------------


class SalesforceMCP:
    """Client for the Salesforce hosted MCP server (sobject-reads)."""

    MCP_URL = "https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads"

    def __init__(self, consumer_key: str, consumer_secret: str, refresh_token: str) -> None:
        access_token = self._get_access_token(consumer_key, consumer_secret, refresh_token)
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {access_token}",
        }
        self.session_id: str | None = None
        self._initialize()

    @staticmethod
    def _get_access_token(consumer_key: str, consumer_secret: str, refresh_token: str) -> str:
        r = requests.post("https://login.salesforce.com/services/oauth2/token", timeout=30, data={
            "grant_type": "refresh_token",
            "client_id": consumer_key,
            "client_secret": consumer_secret,
            "refresh_token": refresh_token,
        })
        r.raise_for_status()
        return r.json()["access_token"]

    def _initialize(self) -> None:
        init_req = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-bench-recorder", "version": "0.1"},
            },
        }
        r = requests.post(self.MCP_URL, json=init_req, headers=self.headers, timeout=30)
        r.raise_for_status()
        session_id = r.headers.get("mcp-session-id")
        if not session_id or not session_id.strip():
            raise RuntimeError(
                "Salesforce MCP initialize response did not include a non-empty "
                "'mcp-session-id' header"
            )
        self.session_id = session_id.strip()
        self.headers["mcp-session-id"] = self.session_id
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        notif_resp = requests.post(self.MCP_URL, json=notif, headers=self.headers, timeout=30)
        notif_resp.raise_for_status()

    def call_tool(self, tool_name: str, arguments: dict) -> tuple[dict, float]:
        req = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        start = time.time()
        r = requests.post(self.MCP_URL, json=req, headers=self.headers, timeout=60)
        wall_ms = (time.time() - start) * 1000
        r.raise_for_status()
        data = r.json()
        result = data.get("result", {})
        structured = result.get("structuredContent")
        if structured:
            return structured, wall_ms
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


def record_salesforce(
    consumer_key: str,
    consumer_secret: str,
    refresh_token: str,
    date: str,
    dry_run: bool = False,
) -> list[tuple[str, Path]]:
    """Record Salesforce native responses via the hosted MCP server (sobject-reads)."""
    results: list[tuple[str, Path]] = []
    if dry_run:
        print("  [dry-run] Would record salesforce-search, salesforce-get")
        return results

    mcp = SalesforceMCP(consumer_key, consumer_secret, refresh_token)

    # Search (SOSL via `find` tool)
    sosl = "FIND {airbyte} IN ALL FIELDS RETURNING Account(Id, Name, Type, Industry LIMIT 10)"
    tool = "find"
    args = {"q": sosl}
    response, wall_ms = mcp.call_tool(tool, args)

    path = save_recording("salesforce-search", [{
        "tool": "mcp__salesforce__find",
        "args": args,
        "wall_clock_ms": round(wall_ms, 1),
        "response": response,
    }], date, "native-mcp")
    results.append(("salesforce-search", path))
    records = response.get("searchRecords", []) if isinstance(response, dict) else []
    print(f"    salesforce-search: {len(records)} records")

    # Get (SOQL via `soqlQuery` tool)
    account_id = "0015e00000FMsFhAAL"
    get_soql = f"SELECT Id, Name, Type, Industry FROM Account WHERE Id = '{account_id}'"
    tool = "soqlQuery"
    args = {"q": get_soql}
    response, wall_ms = mcp.call_tool(tool, args)

    path = save_recording("salesforce-get", [{
        "tool": "mcp__salesforce__soqlQuery",
        "args": args,
        "wall_clock_ms": round(wall_ms, 1),
        "response": response,
    }], date, "native-mcp")
    results.append(("salesforce-get", path))
    print(f"    salesforce-get: {len(json.dumps(response))} bytes")

    return results


# ---------------------------------------------------------------------------
# Zendesk MCP (dunialabs/mcp-zendesk via Docker, stdio)
# ---------------------------------------------------------------------------

ZENDESK_MCP_IMAGE = "ghcr.io/dunialabs/mcp-servers/zendesk:latest"


class ZendeskMCP:
    """MCP client for `dunialabs/mcp-zendesk` (Docker stdio transport, OAuth).

    Tools: `zendeskGetTicket`, `zendeskListTickets`, `zendeskSearchTickets`.
    """

    def __init__(self, subdomain: str, access_token: str) -> None:
        self.proc = subprocess.Popen(  # noqa: S603, S607
            [
                "docker", "run", "-i", "--rm",
                "-e", f"zendeskSubdomain={subdomain}",
                "-e", f"accessToken={access_token}",
                ZENDESK_MCP_IMAGE,
            ],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr,
            text=True,
        )
        try:
            self._initialize()
        except Exception:
            self.proc.terminate()
            self.proc.wait(timeout=5)
            raise

    def _initialize(self) -> None:
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

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=5)


def record_zendesk(subdomain: str, access_token: str, date: str, dry_run: bool = False) -> list[tuple[str, Path]]:
    """Record Zendesk native-mcp via `dunialabs/mcp-zendesk` (Docker, OAuth).

    Tools used:
    - `zendeskSearchTickets` -- keyword/status search
    - `zendeskGetTicket` -- single ticket by ID
    """
    results: list[tuple[str, Path]] = []
    if dry_run:
        print("  [dry-run] Would record zendesk-search, zendesk-get")
        return results

    mcp = ZendeskMCP(subdomain, access_token)

    try:
        # Search
        tool = "zendeskSearchTickets"
        args = {"query": "sync"}
        response, wall_ms = mcp.call_tool(tool, args)
        path = save_recording("zendesk-search", [{
            "tool": f"mcp__zendesk__{tool}",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date, "native-mcp")
        results.append(("zendesk-search", path))
        tickets = response.get("tickets", []) if isinstance(response, dict) else []
        print(f"    zendesk-search: {len(tickets)} tickets (via zendeskSearchTickets)")

        # Get
        tool = "zendeskGetTicket"
        args = {"ticket_id": 2}
        response, wall_ms = mcp.call_tool(tool, args)
        path = save_recording("zendesk-get", [{
            "tool": f"mcp__zendesk__{tool}",
            "args": args,
            "wall_clock_ms": round(wall_ms, 1),
            "response": response,
        }], date, "native-mcp")
        results.append(("zendesk-get", path))
        print(f"    zendesk-get: {len(json.dumps(response))} bytes")

    finally:
        mcp.close()

    return results


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_DEFAULT_CONNECTORS = "linear,slack,gong,salesforce,zendesk"


def record_native_mcp(
    connectors: str | None = None,
    date: str | None = None,
    dry_run: bool = False,
) -> int:
    """Orchestrate recording of all matching native-mcp scenarios.

    Returns 0 on success, 1 on failure.
    """
    date = date or default_date()
    connector_list = [c.strip() for c in (connectors or _DEFAULT_CONNECTORS).split(",")]
    all_results: list[tuple[str, Path]] = []

    for connector in connector_list:
        print(f"\n{'=' * 40}")
        print(f"Recording: {connector}")
        print(f"{'=' * 40}")

        try:
            if connector == "linear":
                api_key = load_secret("linear", "api_key", "test-credentials-api-key")
                all_results.extend(record_linear(api_key, date, dry_run))

            elif connector == "slack":
                bot_token = load_secret("slack", "bot_key", "test-credentials-bot")
                team_id = "T02TET08MDH"
                all_results.extend(record_slack(bot_token, team_id, date, dry_run))

            elif connector == "gong":
                access_key = load_secret("gong", "access_key", "test-credentials-basic")
                access_secret = load_secret("gong", "access_key_secret", "test-credentials-basic")
                all_results.extend(record_gong(access_key, access_secret, date, dry_run))

            elif connector == "salesforce":
                consumer_key = load_secret("salesforce", "consumer_key", "test-credentials-mcp")
                consumer_secret = load_secret("salesforce", "consumer_secret", "test-credentials-mcp")
                refresh_token = load_secret("salesforce", "refresh_token", "test-credentials-mcp")
                if not consumer_key:
                    consumer_key = os.environ.get("SF_MCP_CONSUMER_KEY", "")
                if not consumer_secret:
                    consumer_secret = os.environ.get("SF_MCP_CONSUMER_SECRET", "")
                if not refresh_token:
                    refresh_token = os.environ.get("SF_MCP_REFRESH_TOKEN", "")
                missing = [
                    name for name, val in [
                        ("consumer_key", consumer_key),
                        ("consumer_secret", consumer_secret),
                        ("refresh_token", refresh_token),
                    ] if not val
                ]
                if missing:
                    raise ValueError(
                        f"Salesforce MCP credentials incomplete (missing: {', '.join(missing)}). "
                        "Set 1Password section test-credentials-mcp or env vars "
                        "SF_MCP_CONSUMER_KEY, SF_MCP_CONSUMER_SECRET, SF_MCP_REFRESH_TOKEN"
                    )
                all_results.extend(record_salesforce(consumer_key, consumer_secret, refresh_token, date, dry_run))

            elif connector == "zendesk":
                subdomain = load_secret("zendesk-support", "subdomain", "test-credentials-oauth")
                access_token = load_secret("zendesk-support", "access_token", "test-credentials-oauth")
                all_results.extend(record_zendesk(subdomain, access_token, date, dry_run))

            else:
                print(f"  Unknown connector: {connector}")

        except Exception as e:  # noqa: BLE001
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 40}")
    print(f"Done. Recorded {len(all_results)} scenarios.")
    for scenario, path in all_results:
        print(f"  {scenario} -> {path}")

    return 0
