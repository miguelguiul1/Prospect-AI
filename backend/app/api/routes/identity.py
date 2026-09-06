"""API HTTP mínima do Identity Resolution.

`POST /api/identity/resolve` é uma operação de leitura: recebe os dados de
um candidato (no formato que o Discovery produziria) e devolve a decisão
que o matcher tomaria — sem persistir nada. Serve para inspecionar/depurar
o comportamento do matching sem precisar rodar uma busca de Discovery
completa.

Nenhum endpoint de merge é exposto aqui. `IdentityResolutionService.
merge_companies` (fusão de duas `Company` já existentes) existe e é
testado na camada de serviço, mas fundir duas empresas é uma operação
pouco frequente e de impacto alto — expô-la por HTTP exigiria autenticação
e controle de acesso que este sistema ainda não tem (nenhuma fase até
aqui implementou autenticação). Expor essa rota fica para quando essa
camada existir (Fase 5/dashboard) — ver docs/identity-resolution.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.evidence.enums import ConfidenceLevel
from app.domains.identity.enums import MatchDecision
from app.domains.identity.service import IdentityResolutionService

router = APIRouter(prefix="/api/identity", tags=["identity"])


class IdentityResolveRequest(BaseModel):
    """Mesmo formato de dado que o Discovery produz (`DiscoveredCompany`),
    exposto como schema Pydantic para validação na borda HTTP."""

    source: str = Field(..., max_length=60)
    external_id: str = Field(..., max_length=255)
    name: str | None = None
    formatted_address: str | None = None
    phone: str | None = None
    website: str | None = None
    category: str | None = None
    business_status: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    region_id: uuid.UUID | None = None


class IdentityResolveResponse(BaseModel):
    decision: MatchDecision
    confidence: ConfidenceLevel
    reasons: list[str]
    signals: dict
    matched_company_id: uuid.UUID | None


@router.post("/resolve", response_model=IdentityResolveResponse)
def resolve_identity(payload: IdentityResolveRequest, db: Session = Depends(get_db)) -> IdentityResolveResponse:
    discovered = DiscoveredCompany(
        source=payload.source,
        external_id=payload.external_id,
        name=payload.name,
        formatted_address=payload.formatted_address,
        phone=payload.phone,
        website=payload.website,
        category=payload.category,
        business_status=payload.business_status,
        latitude=payload.latitude,
        longitude=payload.longitude,
        collected_at=datetime.now(timezone.utc),
    )

    service = IdentityResolutionService(db)
    resolution = service.resolve_for_discovery(discovered, region_id=payload.region_id)

    return IdentityResolveResponse(
        decision=resolution.decision,
        confidence=resolution.confidence,
        reasons=resolution.reasons,
        signals=resolution.signals,
        matched_company_id=resolution.matched_company.id if resolution.matched_company else None,
    )
