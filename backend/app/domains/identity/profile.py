"""`CompanyProfile`: a forma comum sob a qual um candidato recém-descoberto
e uma `Company` já persistida são comparados pelo matching (Fase 2).

Reaproveita as funções de normalização já criadas na Fase 1
(`app.domains.discovery.normalization`) — nenhuma lógica de limpeza de
string é duplicada aqui.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domains.companies.models import Company
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.discovery.normalization import (
    normalize_address,
    normalize_category,
    normalize_name,
    normalize_phone,
    normalize_url,
)
from app.domains.evidence.queries import get_current_value
from app.domains.identity.models import CompanySource


@dataclass(frozen=True)
class CompanyProfile:
    """Sinais comparáveis de uma identidade (candidata ou já persistida).

    Todo campo já vem normalizado (ou `None`, quando desconhecido — nunca
    inventado). `label` é só para mensagens de log/erro legíveis, não entra
    na comparação.
    """

    label: str
    name: str | None
    phone: str | None
    address: str | None
    website: str | None
    category: str | None
    region_id: uuid.UUID | None
    latitude: float | None
    longitude: float | None


def build_profile_from_discovered(
    discovered: DiscoveredCompany, *, region_id: uuid.UUID | None
) -> CompanyProfile:
    return CompanyProfile(
        label=f"{discovered.source}:{discovered.external_id}",
        name=normalize_name(discovered.name),
        phone=normalize_phone(discovered.phone),
        address=normalize_address(discovered.formatted_address),
        website=normalize_url(discovered.website),
        category=normalize_category(discovered.category),
        region_id=region_id,
        latitude=discovered.latitude,
        longitude=discovered.longitude,
    )


def build_profile_from_company(db: Session, company: Company) -> CompanyProfile:
    latitude, longitude = _current_coordinates(db, company.id)

    return CompanyProfile(
        label=f"company:{company.id}",
        name=normalize_name(company.canonical_name),
        phone=get_current_value(db, company.id, "phone"),
        address=get_current_value(db, company.id, "address"),
        website=get_current_value(db, company.id, "website"),
        category=get_current_value(db, company.id, "category"),
        region_id=company.region_id,
        latitude=latitude,
        longitude=longitude,
    )


def _current_coordinates(db: Session, company_id: uuid.UUID) -> tuple[float | None, float | None]:
    """Coordenadas da fonte mais recente que informou latitude/longitude.

    `CompanySource` (não `Company`) guarda coordenadas porque elas são um
    dado reportado por uma fonte específica, no mesmo espírito de
    `source_url` — ver docs/data-model.md.
    """
    source = (
        db.query(CompanySource)
        .filter(
            CompanySource.company_id == company_id,
            CompanySource.latitude.is_not(None),
            CompanySource.longitude.is_not(None),
        )
        .order_by(CompanySource.last_seen_at.desc())
        .first()
    )
    if source is None:
        return None, None
    return source.latitude, source.longitude
