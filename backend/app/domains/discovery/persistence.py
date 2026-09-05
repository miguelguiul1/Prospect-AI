"""Persistência de um `DiscoveredCompany` como `Company` + `CompanySource` +
`Evidence`, compatível com a arquitetura v0.2.

Regras que este módulo existe para impor:

- `Company.id` nunca é (nem deriva de) um identificador externo — a ligação
  com a fonte vive inteiramente em `CompanySource`.
- Reprocessar a mesma fonte é idempotente: `(source, external_id)` já
  conhecido nunca cria uma segunda `Company`.
- `Evidence` é append-only — um valor que não mudou desde a última
  observação não gera uma linha nova; um valor que mudou gera uma nova
  linha e marca a antiga como superada. Nunca sobrescreve no lugar.
- Nenhum campo ausente do provider vira uma evidência negativa: só criamos
  `Evidence` para campos que o Discovery de fato observou.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.companies.models import Category, Company, Region
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.discovery.normalization import (
    normalize_address,
    normalize_category,
    normalize_name,
    normalize_phone,
    normalize_url,
)
from app.domains.discovery.schemas import DiscoveryQuery
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.identity.models import CompanySource

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or "categoria"


def find_or_create_region(db: Session, query: DiscoveryQuery) -> Region | None:
    """Resolve a `Region` a partir dos critérios da busca (não do resultado
    individual — ver docs/discovery.md, seção "Por que a região vem da
    busca, não do resultado")."""
    name = query.city or query.region
    if not name:
        return None

    stmt_filters = [func.lower(Region.name) == name.lower(), Region.country == query.country]
    if query.state:
        stmt_filters.append(func.lower(Region.state) == query.state.lower())

    existing = db.query(Region).filter(*stmt_filters).one_or_none()
    if existing is not None:
        return existing

    region = Region(name=name, state=query.state, country=query.country)
    db.add(region)
    db.flush()
    return region


def find_or_create_category(db: Session, category_name: str) -> Category:
    slug = _slugify(category_name)
    existing = db.query(Category).filter(Category.slug == slug).one_or_none()
    if existing is not None:
        return existing

    category = Category(slug=slug, name=category_name.strip().capitalize())
    db.add(category)
    db.flush()
    return category


def find_or_create_company(
    db: Session,
    discovered: DiscoveredCompany,
    *,
    region: Region | None,
    category: Category | None,
) -> tuple[Company, bool]:
    """Retorna `(company, created)`. `created=False` quando a fonte já era
    conhecida — nesse caso apenas `last_seen_at` é atualizado."""
    existing_source = (
        db.query(CompanySource)
        .filter(
            CompanySource.source == discovered.source,
            CompanySource.external_id == discovered.external_id,
        )
        .one_or_none()
    )

    normalized_name = normalize_name(discovered.name) or discovered.external_id

    if existing_source is not None:
        existing_source.raw_reference = discovered.raw_reference
        # last_seen_at é atualizado automaticamente (onupdate) no flush.
        db.flush()
        return existing_source.company, False

    company = Company(
        canonical_name=normalized_name,
        region_id=region.id if region else None,
        category_id=category.id if category else None,
    )
    db.add(company)
    db.flush()

    source = CompanySource(
        company_id=company.id,
        source=discovered.source,
        external_id=discovered.external_id,
        source_url=normalize_url(discovered.source_url),
        confidence=ConfidenceLevel.HIGH,
        raw_reference=discovered.raw_reference,
    )
    db.add(source)
    db.flush()

    return company, True


def _upsert_evidence(
    db: Session,
    *,
    company_id: uuid.UUID,
    field: str,
    value: str,
    source: str,
    source_url: str | None,
) -> None:
    latest = (
        db.query(Evidence)
        .filter(
            Evidence.company_id == company_id,
            Evidence.field == field,
            Evidence.superseded_by_id.is_(None),
        )
        .order_by(Evidence.collected_at.desc())
        .first()
    )

    if latest is not None and latest.value == value and latest.state == DataState.CONFIRMED:
        return  # nada mudou: não gera uma evidência redundante.

    new_evidence = Evidence(
        company_id=company_id,
        field=field,
        value=value,
        state=DataState.CONFIRMED,
        source=source,
        source_url=source_url,
        method=EvidenceMethod.STRUCTURED_FIELD,
        confidence=ConfidenceLevel.HIGH,
    )
    db.add(new_evidence)
    db.flush()

    if latest is not None:
        latest.mark_superseded_by(new_evidence)


def record_evidence(db: Session, company: Company, discovered: DiscoveredCompany) -> None:
    """Cria/atualiza `Evidence` só para os campos que a fonte de fato
    forneceu. Nunca gera evidência para um campo ausente — ausência não é
    o mesmo que "não existe" (arquitetura v0.2, seção 08; Fase 1, seção 6)."""
    normalized_address = normalize_address(discovered.formatted_address)
    normalized_phone = normalize_phone(discovered.phone)
    normalized_website = normalize_url(discovered.website)
    normalized_category = normalize_category(discovered.category)
    normalized_name = normalize_name(discovered.name)

    field_values: list[tuple[str, str | None]] = [
        ("name", normalized_name),
        ("address", normalized_address),
        ("phone", normalized_phone),
        ("website", normalized_website),
        ("category", normalized_category),
        ("business_status", discovered.business_status),
        ("rating", str(discovered.rating) if discovered.rating is not None else None),
        ("review_count", str(discovered.review_count) if discovered.review_count is not None else None),
    ]

    for field, value in field_values:
        if value is None:
            continue
        _upsert_evidence(
            db,
            company_id=company.id,
            field=field,
            value=value,
            source=discovered.source,
            source_url=discovered.source_url,
        )
