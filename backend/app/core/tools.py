"""Tool abstraction shared by built-in integrations and remote MCP servers.

Every capability the investigation engine can invoke (PromQL, log search,
remote MCP tools, ...) is a ``Tool``: a name, a JSON-schema for its arguments and an
async ``run``. Skills never talk to integrations directly; they go through the
``ToolExecutor`` so every call is traced, time-boxed and streamed to the UI.
"""
from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.schemas import DataMode, ToolInfo

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Expected, user-presentable tool failure (bad args, not found, backend down)."""


@dataclass
class ToolResult:
    data: Any
    summary: str
    data_mode: DataMode = "live"


class Tool(ABC):
    name: str
    description: str
    category: str
    input_schema: dict[str, Any]
    source: str = "builtin"
    read_only: bool | None = None

    @property
    def data_mode(self) -> DataMode:
        return "live"

    @abstractmethod
    async def run(self, args: dict[str, Any]) -> ToolResult: ...

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self.name,
            description=self.description,
            category=self.category,
            source=self.source,
            data_mode=self.data_mode,
            input_schema=self.input_schema,
        )


@dataclass
class Param:
    type: str
    description: str
    required: bool = False
    default: Any = None
    enum: list[Any] | None = None


def build_schema(params: dict[str, Param]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for name, p in params.items():
        prop: dict[str, Any] = {"type": p.type, "description": p.description}
        if p.enum:
            prop["enum"] = p.enum
        if p.default is not None:
            prop["default"] = p.default
        props[name] = prop
    return {
        "type": "object",
        "properties": props,
        "required": [n for n, p in params.items() if p.required],
        "additionalProperties": False,
    }


_COERCE: dict[str, Callable[[Any], Any]] = {
    "integer": int,
    "number": float,
    "string": str,
    "boolean": lambda v: v if isinstance(v, bool) else str(v).lower() in {"1", "true", "yes"},
}


@dataclass
class FunctionTool(Tool):
    """Tool backed by an async function whose keyword args match ``params``."""

    name: str
    description: str
    category: str
    params: dict[str, Param]
    func: Callable[..., Awaitable[ToolResult]]
    mode_fn: Callable[[], DataMode] = field(default=lambda: "live")
    source: str = "builtin"

    def __post_init__(self) -> None:
        self.input_schema = build_schema(self.params)

    @property
    def data_mode(self) -> DataMode:
        return self.mode_fn()

    def validate(self, args: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for name, p in self.params.items():
            value = args.get(name)
            if value is None or value == "":
                if p.required:
                    raise ToolError(f"missing required argument '{name}'")
                if p.default is not None:
                    clean[name] = p.default
                continue
            coerce = _COERCE.get(p.type)
            try:
                clean[name] = coerce(value) if coerce else value
            except (TypeError, ValueError) as exc:
                raise ToolError(f"argument '{name}' must be {p.type}") from exc
            if p.enum and clean[name] not in p.enum:
                raise ToolError(f"argument '{name}' must be one of {p.enum}")
        unknown = set(args) - set(self.params)
        if unknown:
            logger.debug("tool %s ignoring unknown args %s", self.name, unknown)
        return clean

    async def run(self, args: dict[str, Any]) -> ToolResult:
        result = self.func(**self.validate(args))
        if inspect.isawaitable(result):
            result = await result
        return result


def tool(
    name: str,
    description: str,
    category: str,
    params: dict[str, Param] | None = None,
    mode_fn: Callable[[], DataMode] | None = None,
) -> Callable[[Callable[..., Awaitable[ToolResult]]], FunctionTool]:
    """Decorator turning an async function into a ``FunctionTool``."""

    def wrap(func: Callable[..., Awaitable[ToolResult]]) -> FunctionTool:
        return FunctionTool(
            name=name,
            description=description,
            category=category,
            params=params or {},
            func=func,
            mode_fn=mode_fn or (lambda: "live"),
        )

    return wrap


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, t: Tool, *, replace: bool = False) -> None:
        if t.name in self._tools and not replace:
            raise ValueError(f"tool '{t.name}' already registered")
        self._tools[t.name] = t

    def register_many(self, tools: list[Tool]) -> None:
        for t in tools:
            self.register(t)

    def unregister_source(self, source: str) -> None:
        for name in [n for n, t in self._tools.items() if t.source == source]:
            del self._tools[name]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def all(self) -> list[Tool]:
        return sorted(self._tools.values(), key=lambda t: (t.category, t.name))

    def __len__(self) -> int:
        return len(self._tools)
