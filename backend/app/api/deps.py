"""FastAPI request dependencies."""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from app.orchestration.service import InvestigationService


async def require_api_key(request: Request) -> None:
    settings = request.app.state.settings
    expected = settings.api_key
    if not expected:
        return
    supplied = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")


def request_user(request: Request) -> str:
    return request.headers.get("X-Forwarded-User", "anonymous").strip()[:200] or "anonymous"


def investigation_service(request: Request) -> InvestigationService:
    return request.app.state.investigation_service