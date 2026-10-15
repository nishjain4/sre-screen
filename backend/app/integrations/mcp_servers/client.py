"""Minimal MCP client (JSON-RPC 2.0) over stdio and streamable HTTP.

Only the client features we need are implemented: ``initialize``, ``tools/list``
(with pagination) and ``tools/call``. No SDK dependency, so the transport is easy
to audit and works on Windows and Linux alike.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import count
import json
from typing import Any

import httpx

from app.config import VERSION
from app.core.tools import ToolError
from app.integrations.mcp_servers.gitea_server import GiteaAPI, handle_message

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "bot-svc-sre", "version": VERSION}


class MCPClient(ABC):
    def __init__(self, name: str, timeout: float) -> None:
        self.name = name
        self.timeout = timeout
        self._ids = count(1)
        self.server_info: dict[str, Any] = {}

    @abstractmethod
    async def _request(self, method: str, params: dict[str, Any] | None) -> Any: ...

    @abstractmethod
    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    async def connect(self) -> None:
        result = await self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO})
        self.server_info = result.get("serverInfo", {}) if isinstance(result, dict) else {}
        await self._notify("notifications/initialized")

    async def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(50):
            result = await self._request("tools/list", {"cursor": cursor} if cursor else {})
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._request("tools/call", {"name": name, "arguments": arguments})

    @staticmethod
    def _unwrap(msg: dict[str, Any]) -> Any:
        if "error" in msg:
            err = msg["error"]
            raise ToolError(f"MCP error {err.get('code')}: {err.get('message')}")
        return msg.get("result", {})


class InProcessGiteaMCPClient(MCPClient):
    """Runs the local Gitea MCP handler without a subprocess (including on Windows)."""

    def __init__(self, name: str, env: dict[str, str], timeout: float) -> None:
        super().__init__(name, timeout)
        base_url = env.get("GITEA_URL", "")
        owner = env.get("GITEA_OWNER", "")
        repo = env.get("GITEA_REPO", "")
        if not base_url or not owner or not repo:
            raise ValueError("GITEA_URL, GITEA_OWNER, and GITEA_REPO must be configured")
        self.api = GiteaAPI(base_url, env.get("GITEA_TOKEN", ""), owner, repo)
        headers = {"Accept": "application/json"}
        if self.api.token:
            headers["Authorization"] = f"token {self.api.token}"
        self.http = httpx.AsyncClient(headers=headers, timeout=timeout)

    async def _request(self, method: str, params: dict[str, Any] | None) -> Any:
        request_id = next(self._ids)
        response = await handle_message(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
            self.api,
            self.http,
        )
        return self._unwrap(response or {})

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await handle_message({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})},
                             self.api, self.http)

    async def close(self) -> None:
        await self.http.aclose()


class HTTPMCPClient(MCPClient):
    """Streamable HTTP MCP with session headers and JSON or SSE responses."""

    def __init__(self, name: str, url: str, headers: dict[str, str], timeout: float) -> None:
        super().__init__(name, timeout)
        self.url = url
        self.http = httpx.AsyncClient(
            headers={**headers, "Accept": "application/json, text/event-stream"},
            timeout=timeout,
        )

    async def connect(self) -> None:
        result = await self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO})
        self.server_info = result.get("serverInfo", {})
        self.http.headers["MCP-Protocol-Version"] = result.get("protocolVersion", PROTOCOL_VERSION)
        await self._notify("notifications/initialized")

    async def _send(self, message: dict[str, Any]) -> Any:
        async with self.http.stream("POST", self.url, json=message) as response:
            response.raise_for_status()
            session = response.headers.get("mcp-session-id")
            if session:
                self.http.headers["Mcp-Session-Id"] = session
            if "id" not in message:
                return None
            if "text/event-stream" in response.headers.get("content-type", ""):
                data: list[str] = []
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data.append(line[5:].lstrip(" "))
                    elif not line and data:
                        payload = json.loads("\n".join(data))
                        data.clear()
                        if isinstance(payload, dict) and payload.get("id") == message["id"]:
                            return self._unwrap(payload)
                raise ToolError("MCP stream ended without a matching response")
            await response.aread()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("id") != message["id"]:
                raise ToolError("MCP server returned an invalid response ID")
            return self._unwrap(payload)

    async def _request(self, method: str, params: dict[str, Any] | None) -> Any:
        return await self._send({
            "jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or {},
        })

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})

    async def close(self) -> None:
        await self.http.aclose()
