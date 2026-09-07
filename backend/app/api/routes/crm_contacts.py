"""API HTTP de Contacts (Fase 7).

Autorização derivada da Opportunity (`app.domains.crm.authorization.
user_owns_any_opportunity_for_company`/`get_accessible_contact_or_404`) —
`Contact` não tem `owner_id` próprio porque pertence a uma `Company`
(entidade compartilhada de inteligência), não a um usuário; ver docstring de
`app.domains.crm.authorization`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.crm.authorization import get_accessible_contact_or_404, user_owns_any_opportunity_for_company
from app.domains.crm.enums import ContactValidationStatus
from app.domains.crm.models import Contact
from app.domains.crm.schemas import ContactCreateRequest, ContactUpdateRequest
from app.domains.crm.service import ContactService

router = APIRouter(prefix="/api/crm/contacts", tags=["crm-contacts"])


class ContactResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    role: str | None
    email: str | None
    phone: str | None
    source: str
    validation_status: ContactValidationStatus
    created_at: datetime
    updated_at: datetime


def _to_response(contact: Contact) -> ContactResponse:
    return ContactResponse(
        id=contact.id,
        company_id=contact.company_id,
        name=contact.name,
        role=contact.role,
        email=contact.email,
        phone=contact.phone,
        source=contact.source,
        validation_status=contact.validation_status,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


def _require_relationship_with_company(db: Session, company_id: uuid.UUID, user: User) -> None:
    if not user_owns_any_opportunity_for_company(db, company_id=company_id, user_id=user.id):
        raise AppError(
            "É necessário ter uma oportunidade para esta empresa antes de gerenciar seus contatos.",
            code="no_opportunity_for_company",
            status_code=status.HTTP_403_FORBIDDEN,
        )


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ContactResponse:
    _require_relationship_with_company(db, payload.company_id, current_user)
    service = ContactService(db)
    try:
        contact = service.create(
            company_id=payload.company_id,
            name=payload.name,
            role=payload.role,
            email=payload.email,
            phone=payload.phone,
            source=payload.source,
        )
    except LookupError as exc:
        raise AppError(str(exc), code="company_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc
    db.commit()
    db.refresh(contact)
    return _to_response(contact)


@router.get("", response_model=list[ContactResponse])
def list_contacts_for_company(
    company_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[ContactResponse]:
    _require_relationship_with_company(db, company_id, current_user)
    contacts = ContactService(db).list_for_company(company_id)
    return [_to_response(c) for c in contacts]


@router.put("/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactResponse:
    contact = get_accessible_contact_or_404(db, contact_id, current_user)
    ContactService(db).update(
        contact,
        name=payload.name,
        role=payload.role,
        email=payload.email,
        phone=payload.phone,
        validation_status=payload.validation_status,
    )
    db.commit()
    db.refresh(contact)
    return _to_response(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    contact = get_accessible_contact_or_404(db, contact_id, current_user)
    ContactService(db).delete(contact)
    db.commit()
