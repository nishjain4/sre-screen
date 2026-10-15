"""Traced, time-boxed tool execution."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.core.tools import ToolError, ToolRegistry
from app.core.gitea_scope import repository_scope
from app.schemas import InvestigationStep, ToolCall, ToolCallStatus, utcnow

logger = logging.getLogger(__name__)

OnCallUpdate = Callable[[InvestigationStep, ToolCall], Awaitable[None]]


def compact(value: Any) -> Any:
    """Copy tool output without dropping details shown in the investigation trace."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [compact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): compact(item) for key, item in value.items()}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass
class ToolOutcome:
    call: ToolCall
    data: Any = None

    @property
    def ok(self) -> bool:
        return self.call.status == ToolCallStatus.SUCCESS

    @property
    def summary(self) -> str:
        return self.call.summary or self.call.error or ""


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        timeout: float,
        concurrency: int,
        on_update: OnCallUpdate,
        query: str = "",
        gitea_url: str | None = None,
    ) -> None:
        self.registry = registry
        self.timeout = timeout
        self._sem = asyncio.Semaphore(concurrency)
        self._on_update = on_update
        self.calls: list[ToolCall] = []
        self.results: dict[str, Any] = {}      # tool_call_id -> full (uncompacted) data
        self._query = query
        self._gitea_url = gitea_url

    async def call(
        self,
        step: InvestigationStep,
        tool_name: str,
        args: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> ToolOutcome:
        args = {k: v for k, v in (args or {}).items() if v is not None}
        tool = self.registry.get(tool_name)
        scope_error: ToolError | None = None
        if tool is not None and tool.source == "mcp:gitea":
            try:
                args.update(repository_scope(self._query, self._gitea_url))
            except ToolError as exc:
                scope_error = exc
        call = ToolCall(tool=tool_name, args=args, description=description)
        step.tool_calls.append(call)
        self.calls.append(call)
        if tool is not None:
            call.data_mode = tool.data_mode
        await self._on_update(step, call)

        data: Any = None
        started = time.perf_counter()
        try:
            if scope_error is not None:
                raise scope_error
            if tool is None:
                raise ToolError(f"tool '{tool_name}' is not registered")
            async with self._sem:
                result = await asyncio.wait_for(tool.run(args), timeout=self.timeout)
            data = result.data
            call.status = ToolCallStatus.SUCCESS
            call.summary = result.summary
            call.data_mode = result.data_mode
            call.output = compact(result.data)
            self.results[call.id] = result.data
        except asyncio.TimeoutError:
            call.status = ToolCallStatus.ERROR
            call.error = f"timed out after {self.timeout:.0f}s"
        except asyncio.CancelledError:
            call.status = ToolCallStatus.ERROR
            call.error = "Tool call cancelled before completion; no result was verified."
            raise
        except ToolError as exc:
            call.status = ToolCallStatus.ERROR
            call.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - a broken integration must not kill the investigation
            logger.exception("tool %s failed", tool_name)
            call.status = ToolCallStatus.ERROR
            call.error = f"{type(exc).__name__}: {exc}"
        finally:
            call.finished_at = utcnow()
            call.duration_ms = int((time.perf_counter() - started) * 1000)
            await self._on_update(step, call)
        return ToolOutcome(call=call, data=data)
