"""FastAPI application and component lifecycle."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import investigations, routes
from app.config import VERSION, get_settings
from app.core.events import EventBus
from app.core.store import SQLiteInvestigationStore
from app.core.tools import ToolRegistry
from app.integrations.mcp_servers.manager import MCPManager
from app.llm.factory import create_llm
from app.orchestration.base import available_orchestrators
from app.orchestration.service import InvestigationService
from app.skills.registry import SkillRegistry



import truststore
from dotenv import load_dotenv


truststore.inject_into_ssl()
load_dotenv()
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    store = SQLiteInvestigationStore(settings.database_path)
    await store.init()
    events = EventBus()
    tools = ToolRegistry()
    llm = create_llm(settings)

    mcp_manager = MCPManager(settings.mcp_config_path, tools, settings.tool_timeout_seconds, {
        "GITEA_URL": settings.gitea_url or "",
        "GITEA_TOKEN": settings.gitea_token or "",
        "GITEA_OWNER": settings.gitea_owner or "",
        "GITEA_REPO": settings.gitea_repo or "",
    })
    await mcp_manager.start()
    skills = SkillRegistry(tools)
    service = InvestigationService(settings, store, events, llm, tools, skills)

    app.state.settings = settings
    app.state.store = store
    app.state.events = events
    app.state.tools = tools
    app.state.llm = llm
    app.state.mcp_manager = mcp_manager
    app.state.skills = skills
    app.state.investigation_service = service
    app.state.available_orchestrators = available_orchestrators
    try:
        yield
    finally:
        await service.shutdown()
        await mcp_manager.stop()
        await llm.aclose()
        store.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes.router)
    app.include_router(investigations.router)
    return app


app = create_app()