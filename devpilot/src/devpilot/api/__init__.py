"""Runtime API surface for the AI Coding governance product."""
from fastapi import APIRouter
from devpilot.api.auth import router as auth_router
from devpilot.api.governance import router as governance_router
from devpilot.api.integrations import router as integrations_router
from devpilot.api.policies import router as policies_router
from devpilot.api.system import router as system_router
from devpilot.api.access import router as access_router
from devpilot.api.scim import router as scim_router
from devpilot.api.budgets import router as budgets_router
from devpilot.api.knowledge import router as knowledge_router
from devpilot.api.agents import router as agents_router
from devpilot.api.dashboard import router as dashboard_router

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
