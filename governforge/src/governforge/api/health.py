"""Kubernetes and container health probes."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from governforge.core.database import engine

router = APIRouter(tags=["health"])

@router.get("/livez")
def livez():
    return {"status": "ok", "service": "governforge-api"}

@router.get("/health")
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "components": {"database": {"healthy": True}}}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "critical", "components": {"database": {"healthy": False}}})
