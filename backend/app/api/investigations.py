"""Investigation API routes and live event stream."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import investigation_service, request_user, require_api_key
from app.core.events import EventBus
from app.orchestration.export import export_payload
from app.orchestration.service import InvestigationNotFound, InvestigationService
from app.schemas import (ChatRequest, FeedbackRequest, InvestigationCreate, InvestigationStatus)

router = APIRouter(prefix="/api/investigations", dependencies=[Depends(require_api_key)])


def _not_found(exc: InvestigationNotFound) -> HTTPException:
    return HTTPException(status_code=404, detail="Investigation not found")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_investigation(payload: InvestigationCreate, request: Request,
                               service: InvestigationService = Depends(investigation_service)):
    return await service.start(payload, request_user(request))


@router.get("")
async def list_investigations(
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    service: InvestigationService = Depends(investigation_service),
):
    return await service.list(limit, offset, q)


@router.get("/{inv_id}")
async def get_investigation(inv_id: str, service: InvestigationService = Depends(investigation_service)):
    try:
        return await service.get(inv_id)
    except InvestigationNotFound as exc:
        raise _not_found(exc)


@router.delete("/{inv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_investigation(inv_id: str, service: InvestigationService = Depends(investigation_service)):
    try:
        await service.delete(inv_id)
    except InvestigationNotFound as exc:
        raise _not_found(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{inv_id}/cancel")
async def cancel_investigation(inv_id: str, service: InvestigationService = Depends(investigation_service)):
    try:
        return await service.cancel(inv_id)
    except InvestigationNotFound as exc:
        raise _not_found(exc)


@router.get("/{inv_id}/events")
async def investigation_events(inv_id: str, request: Request,
                               service: InvestigationService = Depends(investigation_service)):
    try:
        await service.get(inv_id)
    except InvestigationNotFound as exc:
        raise _not_found(exc)
    events: EventBus = request.app.state.events

    async def stream():
        async with events.subscribe(inv_id) as queue:
            current = await service.get(inv_id)
            yield _sse("snapshot", current.model_dump(mode="json"))
            if current.status not in (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING):
                yield _sse("done", {"status": current.status.value})
                return
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse(event.type, event.data)
                if event.type == "done":
                    return

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/{inv_id}/chat")
async def chat(inv_id: str, payload: ChatRequest,
               service: InvestigationService = Depends(investigation_service)):
    try:
        return await service.chat(inv_id, payload.message)
    except InvestigationNotFound as exc:
        raise _not_found(exc)


@router.post("/{inv_id}/feedback")
async def feedback(inv_id: str, payload: FeedbackRequest,
                   service: InvestigationService = Depends(investigation_service)):
    try:
        return await service.feedback(inv_id, payload.helpful, payload.comment)
    except InvestigationNotFound as exc:
        raise _not_found(exc)


@router.get("/{inv_id}/export")
async def export_investigation(inv_id: str, format: str = Query(default="markdown", pattern="^(markdown|json)$"),
                               service: InvestigationService = Depends(investigation_service)):
    try:
        inv = await service.get(inv_id)
    except InvestigationNotFound as exc:
        raise _not_found(exc)
    body, media_type, extension = export_payload(inv, format)
    filename = f"investigation-{inv.id}.{extension}"
    return Response(content=body, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})