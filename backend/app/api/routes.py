"""General API catalog routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_api_key
from app.config import VERSION
from app.schemas import ServiceConfig
from app.templates import load_templates

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": VERSION}


@router.get("/config", response_model=ServiceConfig)
async def config(request: Request) -> ServiceConfig:
    settings = request.app.state.settings
    llm = request.app.state.llm
    mcp = request.app.state.mcp_manager
    return ServiceConfig(
        llm_provider=llm.name, llm_model=llm.model, llm_configured=llm.available,
        orchestrator=settings.orchestrator,
        available_orchestrators=request.app.state.available_orchestrators(),
        mcp_servers=mcp.status(),
        version=VERSION,
    )


@router.get("/skills")
async def skills(request: Request):
    return request.app.state.skills.infos()


@router.get("/tools")
async def tools(request: Request):
    return [item.info() for item in request.app.state.tools.all()]


@router.get("/templates")
async def templates(request: Request):
    return load_templates(request.app.state.settings.templates_path)