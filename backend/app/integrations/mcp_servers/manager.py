"""Connects configured MCP servers and registers their tools in the ToolRegistry."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from app.core.tools import Tool, ToolError, ToolRegistry, ToolResult
from app.integrations.mcp_servers.client import HTTPMCPClient, InProcessGiteaMCPClient, MCPClient
from app.schemas import DataMode, MCPServerStatus

logger = logging.getLogger(__name__)

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value: Any, environment: dict[str, str] | None = None) -> Any:
    variables = {**os.environ, **(environment or {})}
    if isinstance(value, str):
        return _ENV.sub(lambda m: variables.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: expand_env(v, environment) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v, environment) for v in value]
    return value


class RemoteMCPTool(Tool):
    def __init__(self, server: str, client: MCPClient, spec: dict[str, Any], category: str) -> None:
        self.server = server
        self.client = client
        self.remote_name = spec["name"]
        self.name = f"{server}__{spec['name']}"
        self.description = (spec.get("description") or spec.get("title") or spec["name"])[:1000]
        self.category = category
        self.input_schema = spec.get("inputSchema") or {"type": "object", "properties": {}}
        self.source = f"mcp:{server}"
        hint = (spec.get("annotations") or {}).get("readOnlyHint")
        self.read_only = hint if isinstance(hint, bool) else None

    @property
    def data_mode(self) -> DataMode:
        return "mcp"

    async def run(self, args: dict[str, Any]) -> ToolResult:
        allowed = set(self.input_schema.get("properties", {}))
        clean = {k: v for k, v in args.items() if not allowed or k in allowed}
        result = await self.client.call_tool(self.remote_name, clean)
        texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        data: Any = result.get("structuredContent")
        if data is None:
            joined = "\n".join(texts)
            try:
                data = json.loads(joined)
            except (json.JSONDecodeError, ValueError):
                data = {"text": joined}
        if result.get("isError"):
            raise ToolError(("\n".join(texts) or "remote tool error")[:500])
        first = (texts[0] if texts else json.dumps(data, default=str)).strip().replace("\n", " ")
        return ToolResult(data, f"{self.name}: {first[:200]}", "mcp")


class MCPManager:
    def __init__(self, config_path: Path, registry: ToolRegistry, timeout: float,
                 environment: dict[str, str] | None = None) -> None:
        self.config_path = config_path
        self.registry = registry
        self.timeout = timeout
        self.environment = environment or {}
        self.clients: dict[str, MCPClient] = {}
        self.statuses: dict[str, MCPServerStatus] = {}

    def _load(self) -> list[dict[str, Any]]:
        if not self.config_path.exists():
            logger.warning("MCP configuration file not found: %s; no servers will be registered", self.config_path)
            return []
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        return raw.get("servers", []) or []

    async def start(self) -> None:
        servers = self._load()
        await asyncio.gather(*(self._start_one(s) for s in servers))

    async def _start_one(self, cfg: dict[str, Any]) -> None:
        name = cfg.get("name", "unnamed")
        transport = cfg.get("transport", "stdio")
        if not cfg.get("enabled", False):
            self.statuses[name] = MCPServerStatus(name=name, transport=transport, status="disabled")
            return
        cfg = expand_env(cfg, self.environment)
        client: MCPClient | None = None
        try:
            if transport == "http":
                client = HTTPMCPClient(name, cfg["url"], cfg.get("headers") or {}, self.timeout)
            elif name == "gitea" and transport == "inprocess":
                client = InProcessGiteaMCPClient(name, cfg.get("env") or {}, self.timeout)
            else:
                raise ValueError(f"Unsupported MCP transport: {transport}")
            await asyncio.wait_for(client.connect(), timeout=self.timeout * 2)
            specs = await client.list_tools()
            include = set(cfg.get("include_tools") or [])
            category = cfg.get("category", "mcp")
            tools = [RemoteMCPTool(name, client, s, category) for s in specs if not include or s["name"] in include]
            self.registry.unregister_source(f"mcp:{name}")
            for t in tools:
                self.registry.register(t, replace=True)
            self.clients[name] = client
            self.statuses[name] = MCPServerStatus(name=name, transport=transport, status="connected", tool_count=len(tools))
            logger.info("MCP server %s connected with %d tools", name, len(tools))
        except Exception as exc:  # noqa: BLE001 - a broken server must never block startup
            if client is not None:
                await client.close()
            logger.warning("MCP server %s failed: %s", name, exc)
            self.statuses[name] = MCPServerStatus(name=name, transport=transport, status="error",
                                                  error=str(exc) or type(exc).__name__)

    def status(self) -> list[MCPServerStatus]:
        return list(self.statuses.values())

    async def stop(self) -> None:
        for name, client in self.clients.items():
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                logger.debug("error closing MCP server %s", name, exc_info=True)
            self.registry.unregister_source(f"mcp:{name}")
        self.clients.clear()
