"""API HTTP de Activities (notas, tarefas, timeline) — Fase 7.

Autorização sempre derivada da `Opportunity` dona da atividade (ver
`app.domains.crm.authorization.get_owned_activity_or_404`) — nunca existe
`owner_id` próprio em `Activity`.
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
from app.domains.crm.authorization import get_owned_activity_or_404, get_owned_opportunity_or_404
from app.domains.crm.models import Activity
from app.domains.crm.schemas import ActivityCreateRequest, ActivityUpdateRequest
from app.domains.crm.service import ActivityService

router = APIRouter(prefix="/api/crm/activities", tags=["crm-activities"])


class ActivityResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    type: str
    title: str | None
    description: str | None
    status: str | None
    due_at: datetime | None
    completed_at: datetime | None
    context: dict | None
    created_by: uuid.UUID
    created_at: datetime


def _to_response(activity: Activity) -> ActivityResponse:
    return ActivityResponse(
        id=activity.id,
        opportunity_id=activity.opportunity_id,
        type=activity.type.value,
        title=activity.title,
        description=activity.description,
        status=activity.status.value if activity.status else None,
        due_at=activity.due_at,
        completed_at=activity.completed_at,
        context=activity.context,
        created_by=activity.created_by,
        created_at=activity.created_at,
    )


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def create_activity(
    payload: ActivityCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ActivityResponse:
    get_owned_opportunity_or_404(db, payload.opportunity_id, current_user)
    activity = ActivityService(db).create(
        opportunity_id=payload.opportunity_id,
        type_=payload.type,
        created_by=current_user.id,
        title=payload.title,
        description=payload.description,
        due_at=payload.due_at,
    )
    db.commit()
    db.refresh(activity)
    return _to_response(activity)


@router.put("/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: uuid.UUID,
    payload: ActivityUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityResponse:
    activity = get_owned_activity_or_404(db, activity_id, current_user)
    try:
        ActivityService(db).update(
            activity,
            title=payload.title,
            description=payload.description,
            due_at=payload.due_at,
            completed=payload.completed,
        )
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_activity_update", status_code=status.HTTP_422_UNPROCESSABLE_CONTENT) from exc
    db.commit()
    db.refresh(activity)
    return _to_response(activity)


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    activity_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    activity = get_owned_activity_or_404(db, activity_id, current_user)
    try:
        ActivityService(db).delete(activity)
    except ValueError as exc:
        raise AppError(str(exc), code="activity_not_deletable", status_code=status.HTTP_409_CONFLICT) from exc
    db.commit()
