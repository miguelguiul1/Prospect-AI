"""Agregador de routers da API. Novos domínios registram seus routers aqui
conforme forem implementados nas fases futuras."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    audit,
    auth,
    companies,
    crm_activities,
    crm_contacts,
    crm_opportunities,
    discovery,
    health,
    identity,
    metrics,
    outreach,
    prototypes,
    sales_brief,
    scoring,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(metrics.router)
api_router.include_router(auth.router)
api_router.include_router(discovery.router)
api_router.include_router(identity.router)
api_router.include_router(audit.router)
api_router.include_router(scoring.router)
api_router.include_router(sales_brief.router)
api_router.include_router(companies.router)
api_router.include_router(prototypes.router)
api_router.include_router(crm_opportunities.router)
api_router.include_router(crm_contacts.router)
api_router.include_router(crm_activities.router)
api_router.include_router(outreach.router)
