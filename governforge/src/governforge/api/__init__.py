"""Runtime API surface for the AI Coding governance product."""
from fastapi import APIRouter
from governforge.api.auth import router as auth_router
from governforge.api.governance import router as governance_router
from governforge.api.integrations import router as integrations_router
from governforge.api.policies import router as policies_router
from governforge.api.system import router as system_router
from governforge.api.access import router as access_router
from governforge.api.scim import router as scim_router
from governforge.api.budgets import router as budgets_router
from governforge.api.knowledge import router as knowledge_router
from governforge.api.agents import router as agents_router
from governforge.api.dashboard import router as dashboard_router
from governforge.api.agent_events import router as agent_events_router
from governforge.api.model_gateway import router as model_gateway_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(governance_router, prefix="/governance", tags=["governance"])
api_router.include_router(integrations_router, prefix="/integrations", tags=["integrations"])
api_router.include_router(policies_router, prefix="/policies", tags=["policies"])
api_router.include_router(system_router, prefix="/system", tags=["system"])
api_router.include_router(access_router, prefix="/access", tags=["access"])
api_router.include_router(scim_router, prefix="/scim/v2", tags=["scim"])
api_router.include_router(budgets_router, prefix="/budgets", tags=["budgets"])
api_router.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(agent_events_router, prefix="/agent-events", tags=["agent-events"])
api_router.include_router(model_gateway_router, prefix="/model-gateway", tags=["model-gateway"])
