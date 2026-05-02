"""Real-MCP client and OAuth handling for `mcp.airbyte.ai`.

This module is what makes the Agent MCP path actually use MCP. It speaks
JSON-RPC over Streamable HTTP to the hosted MCP server and uses the
official MCP SDK's `OAuthClientProvider` for browser-based PKCE auth.

Tokens persist to ``~/.airbyte/agent-mcp-tokens.json`` so subsequent runs
refresh automatically. The refresh token has an approximately 60-day TTL;
after it expires the user must re-auth in a browser.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)


DEFAULT_MCP_URL = "https://mcp.airbyte.ai/mcp"
DEFAULT_TOKEN_PATH = Path.home() / ".airbyte" / "agent-mcp-tokens.json"
CLIENT_NAME = "airbyte-agents-benchmarks"


class FileTokenStorage(TokenStorage):
    """Persist OAuth tokens + DCR client info to a single JSON file.

    Layout:
        {
          "client_info": {...OAuthClientInformationFull...},
          "tokens": {...OAuthToken...}
        }
    """

    def __init__(self, path: Path = DEFAULT_TOKEN_PATH) -> None:
        self.path = path

    def _read(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._read().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json")
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json")
        self._write(data)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class _CallbackResult:
    code: str | None = None
    state: str | None = None
    error: str | None = None


def _make_callback_server(port: int, result: _CallbackResult, done: threading.Event) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            params = parse_qs(urlparse(self.path).query)
            result.code = params.get("code", [None])[0]
            result.state = params.get("state", [None])[0]
            result.error = params.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            body = (
                "<h2>Authorization complete.</h2>"
                "<p>You can close this tab and return to the terminal.</p>"
                if result.error is None
                else f"<h2>Authorization failed: {result.error}</h2>"
            )
            self.wfile.write(body.encode())
            done.set()

        def log_message(self, *args, **kwargs):  # silence default stderr noise
            pass

    return HTTPServer(("127.0.0.1", port), Handler)


def make_oauth_provider(
    server_url: str = DEFAULT_MCP_URL,
    storage: TokenStorage | None = None,
    timeout_seconds: float = 300.0,
) -> OAuthClientProvider:
    """Build an OAuthClientProvider that drives a one-shot localhost browser flow.

    Picks a free localhost port, registers it as the redirect URI via DCR,
    opens the user's default browser, runs a single-request HTTP server to
    receive the callback, and returns the auth code to the SDK.
    """
    storage = storage or FileTokenStorage()
    callback_port = _free_port()
    redirect_uri = f"http://127.0.0.1:{callback_port}/callback"

    client_metadata = OAuthClientMetadata(
        client_name=CLIENT_NAME,
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )

    async def redirect_handler(authorization_url: str) -> None:
        print(f"\nOpening browser to authenticate with {server_url} ...")
        print("If the browser does not open automatically, visit this URL:")
        print(f"  {authorization_url}\n")
        webbrowser.open(authorization_url)

    async def callback_handler() -> tuple[str, str | None]:
        result = _CallbackResult()
        done = threading.Event()
        server = _make_callback_server(callback_port, result, done)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            ready = await asyncio.get_event_loop().run_in_executor(
                None, done.wait, timeout_seconds
            )
        finally:
            server.shutdown()
            server.server_close()
        if not ready:
            raise TimeoutError("Timed out waiting for OAuth redirect to localhost")
        if result.error or not result.code:
            raise RuntimeError(f"OAuth flow failed: {result.error or 'no code returned'}")
        return result.code, result.state

    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=timeout_seconds,
    )


class AirbyteMCPClient:
    """Streamable HTTP MCP client for `mcp.airbyte.ai` with OAuth.

    Mirrors the shape of the LinearMCP / SalesforceMCP clients in
    `agent_bench.recording.native_mcp_recorder`: `initialize()` then
    `call_tool(name, args)` returning `(parsed_response, wall_clock_ms)`.
    The auth provider handles login + refresh transparently.
    """

    def __init__(
        self,
        server_url: str = DEFAULT_MCP_URL,
        organization_id: str | None = None,
        storage: TokenStorage | None = None,
    ) -> None:
        self.server_url = server_url
        self.organization_id = organization_id
        self.auth = make_oauth_provider(server_url=server_url, storage=storage)
        self._client = httpx.AsyncClient(auth=self.auth, timeout=60.0)
        self._session_id: str | None = None
        self._next_id = 1

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.organization_id:
            h["X-Organization-Id"] = self.organization_id
        if self._session_id:
            h["mcp-session-id"] = self._session_id
        return h

    async def initialize(self) -> None:
        init_req = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": "0.1"},
            },
        }
        self._next_id += 1
        resp = await self._client.post(
            self.server_url, json=init_req, headers=self._headers()
        )
        resp.raise_for_status()
        # Streamable HTTP returns the session id in the response header
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        # Send notifications/initialized to complete the handshake
        notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        notif_resp = await self._client.post(
            self.server_url, json=notif, headers=self._headers()
        )
        notif_resp.raise_for_status()

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[Any, float]:
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        self._next_id += 1
        t0 = time.perf_counter()
        resp = await self._client.post(
            self.server_url, json=req, headers=self._headers()
        )
        wall_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        return _parse_jsonrpc_payload(resp.text), wall_ms

    async def close(self) -> None:
        await self._client.aclose()


def _parse_jsonrpc_payload(text: str) -> Any:
    """Parse a Streamable HTTP MCP response (JSON or SSE) and return the
    inner tool result.

    The MCP server may return either ``application/json`` (plain JSON-RPC
    body) or ``text/event-stream`` (SSE-framed JSON-RPC). Tool results
    expose ``structuredContent`` (preferred) or a ``content[0].text`` blob
    that is itself a JSON string.
    """
    candidates: list[dict] = []
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            candidates.append(json.loads(stripped))
        except json.JSONDecodeError:
            pass
    if not candidates:
        for line in text.split("\n"):
            if line.startswith("data:"):
                try:
                    candidates.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    continue
    if not candidates:
        return {"error": "no parseable response", "raw": text}
    msg = next((c for c in candidates if "result" in c or "error" in c), candidates[0])
    if "error" in msg and msg["error"]:
        return {"error": msg["error"]}
    result = msg.get("result", {})
    if isinstance(result, dict):
        if "structuredContent" in result and result["structuredContent"] is not None:
            return result["structuredContent"]
        content = result.get("content")
        if isinstance(content, list) and content:
            text_blob = content[0].get("text", "")
            try:
                return json.loads(text_blob)
            except json.JSONDecodeError:
                return {"text": text_blob}
    return result
