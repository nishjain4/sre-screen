"""Investigation lifecycle, persistence, events, chat, and feedback."""
from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.core.events import EventBus
from app.core.store import InvestigationStore
from app.core.tools import ToolRegistry
from app.llm.base import LLMProvider
from app.orchestration.base import OrchestratorDeps, create_orchestrator
from app.schemas import (ChatMessage, Feedback, Investigation, InvestigationCreate, InvestigationList,
                         InvestigationStatus, utcnow)
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class InvestigationNotFound(LookupError):
    pass


class InvestigationService:
    def __init__(self, settings: Settings, store: InvestigationStore, events: EventBus,
                 llm: LLMProvider, tools: ToolRegistry, skills: SkillRegistry) -> None:
        self.settings = settings
        self.store = store
        self.events = events
        self.llm = llm
        self.deps = OrchestratorDeps(settings, llm, tools, skills)
        self._limit = asyncio.Semaphore(max(1, settings.max_concurrent_investigations))
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def start(self, request: InvestigationCreate, user: str = "anonymous") -> Investigation:
        inv = Investigation(
            title=request.query.strip().splitlines()[0][:90], query=request.query,
            mode=request.mode, requested_skill_ids=list(request.skill_ids), context=dict(request.context),
            template_id=request.template_id, initiated_by=user, orchestrator=self.settings.orchestrator,
            llm=self.llm.label,
        )
        await self.store.save(inv)
        task = asyncio.create_task(self._run(inv), name=f"investigation:{inv.id}")
        self._tasks[inv.id] = task
        task.add_done_callback(lambda _: self._tasks.pop(inv.id, None))
        await self._publish(inv, "snapshot", inv.model_dump(mode="json"))
        return inv

    async def _run(self, inv: Investigation) -> None:
        try:
            async with self._limit:
                async with self._lock:
                    if inv.status == InvestigationStatus.CANCELLED:
                        return
                    inv.status = InvestigationStatus.RUNNING
                    inv.started_at = utcnow()
                    await self._save_status(inv)
                orchestrator = create_orchestrator(inv.orchestrator or self.settings.orchestrator, self.deps)

                async def publish(event: str, data) -> None:
                    await self._publish(inv, event, data)

                async def persist() -> None:
                    await self.store.save(inv)

                from app.orchestration.base import RunContext

                await orchestrator.run(RunContext(inv, self.deps, publish, persist))
                if inv.status not in (InvestigationStatus.CANCELLED, InvestigationStatus.FAILED):
                    inv.status = InvestigationStatus.COMPLETED
                    inv.outcome = inv.outcome or "inconclusive"
                    await self._finish(inv)
        except asyncio.CancelledError:
            if inv.status != InvestigationStatus.CANCELLED:
                inv.status = InvestigationStatus.CANCELLED
                inv.error = "Investigation cancelled."
                await self._finish(inv)
        except Exception as exc:  # noqa: BLE001 - fail one investigation without taking down the API
            logger.exception("investigation %s failed", inv.id)
            inv.status = InvestigationStatus.FAILED
            inv.error = f"{type(exc).__name__}: {exc}"[:1000]
            await self._finish(inv)

    async def _finish(self, inv: Investigation) -> None:
        inv.finished_at = utcnow()
        if inv.started_at:
            inv.duration_ms = int((inv.finished_at - inv.started_at).total_seconds() * 1000)
        await self.store.save(inv)
        await self._publish(inv, "status", self._status_payload(inv))
        await self._publish(inv, "done", {"status": inv.status.value})

    async def _save_status(self, inv: Investigation) -> None:
        await self.store.save(inv)
        await self._publish(inv, "status", self._status_payload(inv))

    @staticmethod
    def _status_payload(inv: Investigation) -> dict:
        return {
            "status": inv.status.value, "outcome": inv.outcome, "title": inv.title,
            "selected_skill_ids": inv.selected_skill_ids,
            "started_at": inv.started_at.isoformat() if inv.started_at else None,
            "finished_at": inv.finished_at.isoformat() if inv.finished_at else None,
            "duration_ms": inv.duration_ms, "error": inv.error,
        }

    async def _publish(self, inv: Investigation, event: str, data) -> None:
        await self.events.publish(inv.id, event, data)

    async def get(self, inv_id: str) -> Investigation:
        inv = await self.store.get(inv_id)
        if inv is None:
            raise InvestigationNotFound(inv_id)
        return inv

    async def list(self, limit: int = 50, offset: int = 0, q: str | None = None) -> InvestigationList:
        items, total = await self.store.list(limit, offset, q)
        items.sort(key=lambda item: (
            item.status not in (InvestigationStatus.RUNNING, InvestigationStatus.QUEUED),
            -item.created_at.timestamp(),
        ))
        return InvestigationList(items=items, total=total)

    async def cancel(self, inv_id: str) -> Investigation:
        inv = await self.get(inv_id)
        if inv.status in (InvestigationStatus.RUNNING, InvestigationStatus.QUEUED):
            inv.status = InvestigationStatus.CANCELLED
            inv.error = "Investigation cancelled."
            await self._finish(inv)
            task = self._tasks.get(inv_id)
            if task and not task.done():
                task.cancel()
        return inv

    async def delete(self, inv_id: str) -> bool:
        inv = await self.get(inv_id)
        if inv.status in (InvestigationStatus.RUNNING, InvestigationStatus.QUEUED):
            await self.cancel(inv_id)
        deleted = await self.store.delete(inv_id)
        if not deleted:
            raise InvestigationNotFound(inv_id)
        return True

    async def chat(self, inv_id: str, message: str) -> ChatMessage:
        inv = await self.get(inv_id)
        answer = await create_orchestrator(inv.orchestrator or self.settings.orchestrator, self.deps).chat(inv, message)
        inv.chat.append(ChatMessage(role="user", content=message))
        reply = ChatMessage(role="assistant", content=answer)
        inv.chat.append(reply)
        await self.store.save(inv)
        await self._publish(inv, "chat", reply.model_dump(mode="json"))
        return reply

    async def feedback(self, inv_id: str, helpful: bool, comment: str | None = None) -> Feedback:
        inv = await self.get(inv_id)
        inv.feedback = Feedback(helpful=helpful, comment=comment)
        await self.store.save(inv)
        return inv.feedback

    async def shutdown(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)