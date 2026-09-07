"""Orquestração do domínio `crm` (Fase 7): Opportunity, Pipeline, Contact,
Activity.

Nenhum destes serviços reimplementa Discovery/Identity/Audit/Scoring/Sales
Brief — todos leem `Company` só por `company_id` (nunca copiam campos) e
delegam Opportunity Score/Sales Brief a `app.domains.scoring`/
`app.domains.briefing` na camada de leitura da API (ver
`app.api.routes.crm_opportunities._to_detail_response`), nunca aqui.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.companies.models import Company
from app.domains.crm.enums import (
    ActivityStatus,
    ActivityType,
    ContactValidationStatus,
    OpportunityPriority,
    OpportunityStatus,
)
from app.domains.crm.models import Activity, Contact, Opportunity, PipelineStage

_DELETABLE_ACTIVITY_TYPES = {ActivityType.NOTE, ActivityType.TASK, ActivityType.CALL, ActivityType.MEETING, ActivityType.EMAIL, ActivityType.WHATSAPP}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log_activity(
    db: Session,
    *,
    opportunity_id: uuid.UUID,
    type_: ActivityType,
    created_by: uuid.UUID,
    title: str | None = None,
    description: str | None = None,
    context: dict | None = None,
    status: ActivityStatus | None = None,
    due_at: datetime | None = None,
) -> Activity:
    activity = Activity(
        opportunity_id=opportunity_id,
        type=type_,
        title=title,
        description=description,
        context=context,
        status=status,
        due_at=due_at,
        created_by=created_by,
    )
    db.add(activity)
    db.flush()
    return activity


class PipelineService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_stages(self) -> list[PipelineStage]:
        return self._db.query(PipelineStage).order_by(PipelineStage.order).all()

    def get_by_key(self, key: str) -> PipelineStage | None:
        return self._db.query(PipelineStage).filter(PipelineStage.key == key).first()

    def default_stage(self) -> PipelineStage:
        stage = self._db.query(PipelineStage).order_by(PipelineStage.order).first()
        if stage is None:
            raise LookupError("Nenhum PipelineStage configurado — rode as migrations até a 0008.")
        return stage

    def terminal_stage(self, *, won: bool) -> PipelineStage:
        query = self._db.query(PipelineStage)
        stage = query.filter(PipelineStage.is_won.is_(True)).first() if won else query.filter(PipelineStage.is_lost.is_(True)).first()
        if stage is None:
            raise LookupError("Nenhuma etapa terminal (ganho/perdido) configurada.")
        return stage


@dataclass(frozen=True)
class OpportunityPage:
    items: list[Opportunity]
    total: int
    limit: int
    offset: int


class OpportunityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create_or_get(
        self, *, company_id: uuid.UUID, owner_id: uuid.UUID, priority: OpportunityPriority
    ) -> tuple[Opportunity, bool]:
        """Idempotente (Prompt 11, seção 6): se já existe uma `Opportunity`
        `OPEN` para esta empresa, devolve ela (`created=False`) em vez de
        criar uma duplicata. Protegido também no banco (índice único parcial
        em `Opportunity.__table_args__`) contra a corrida de duas
        requisições simultâneas — ver seção 24 do Prompt 11."""
        company = self._db.get(Company, company_id)
        if company is None:
            raise LookupError(f"Company {company_id} não encontrada")

        existing = self._get_open_for_company(company_id)
        if existing is not None:
            return existing, False

        default_stage = PipelineService(self._db).default_stage()
        opportunity = Opportunity(
            company_id=company_id,
            owner_id=owner_id,
            stage_id=default_stage.id,
            status=OpportunityStatus.OPEN,
            priority=priority,
        )
        self._db.add(opportunity)
        try:
            self._db.flush()
        except IntegrityError:
            self._db.rollback()
            existing = self._get_open_for_company(company_id)
            if existing is None:
                raise
            return existing, False

        log_activity(
            self._db,
            opportunity_id=opportunity.id,
            type_=ActivityType.SYSTEM,
            created_by=owner_id,
            title="Oportunidade criada",
        )
        return opportunity, True

    def _get_open_for_company(self, company_id: uuid.UUID) -> Opportunity | None:
        return (
            self._db.query(Opportunity)
            .filter(Opportunity.company_id == company_id, Opportunity.status == OpportunityStatus.OPEN)
            .first()
        )

    def get_open_for_company(self, company_id: uuid.UUID) -> Opportunity | None:
        return self._get_open_for_company(company_id)

    def list_for_owner(
        self,
        owner_id: uuid.UUID,
        *,
        stage_key: str | None = None,
        status_filter: OpportunityStatus | None = None,
        priority: OpportunityPriority | None = None,
        category_id: uuid.UUID | None = None,
        region_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> OpportunityPage:
        query = self._db.query(Opportunity).filter(Opportunity.owner_id == owner_id)
        if stage_key is not None:
            stage = PipelineService(self._db).get_by_key(stage_key)
            query = query.filter(Opportunity.stage_id == (stage.id if stage else uuid.uuid4()))
        if status_filter is not None:
            query = query.filter(Opportunity.status == status_filter)
        if priority is not None:
            query = query.filter(Opportunity.priority == priority)
        if category_id is not None or region_id is not None:
            query = query.join(Company, Company.id == Opportunity.company_id)
            if category_id is not None:
                query = query.filter(Company.category_id == category_id)
            if region_id is not None:
                query = query.filter(Company.region_id == region_id)

        total = query.count()
        items = query.order_by(Opportunity.updated_at.desc()).limit(limit).offset(offset).all()
        return OpportunityPage(items=items, total=total, limit=limit, offset=offset)

    def change_stage(self, opportunity: Opportunity, *, stage_key: str, user_id: uuid.UUID) -> Opportunity:
        if opportunity.status != OpportunityStatus.OPEN:
            raise ValueError("Não é possível mudar a etapa de uma oportunidade que não está aberta.")

        new_stage = PipelineService(self._db).get_by_key(stage_key)
        if new_stage is None:
            raise ValueError(f"Etapa '{stage_key}' não existe.")

        old_stage = opportunity.stage
        # Atribui o objeto de relacionamento (não só `stage_id`) para que o
        # atributo `opportunity.stage` já reflita o novo valor imediatamente
        # em memória — setar só a FK deixaria `.stage` com o objeto antigo
        # em cache até a próxima expiração/refresh da sessão.
        opportunity.stage = new_stage
        if new_stage.is_won:
            opportunity.status = OpportunityStatus.WON
            opportunity.closed_at = _now()
        elif new_stage.is_lost:
            opportunity.status = OpportunityStatus.LOST
            opportunity.closed_at = _now()
        self._db.flush()

        log_activity(
            self._db,
            opportunity_id=opportunity.id,
            type_=ActivityType.STAGE_CHANGE,
            created_by=user_id,
            title=f"Etapa alterada: {old_stage.name} → {new_stage.name}",
            context={"from_stage": old_stage.key, "to_stage": new_stage.key},
        )
        return opportunity

    def close(self, opportunity: Opportunity, *, outcome: str, reason: str | None, user_id: uuid.UUID) -> Opportunity:
        if opportunity.status != OpportunityStatus.OPEN:
            raise ValueError("Esta oportunidade já está encerrada.")
        terminal_stage = PipelineService(self._db).terminal_stage(won=(outcome == "won"))
        result = self.change_stage(opportunity, stage_key=terminal_stage.key, user_id=user_id)
        if reason:
            log_activity(
                self._db,
                opportunity_id=opportunity.id,
                type_=ActivityType.NOTE,
                created_by=user_id,
                title="Motivo do encerramento",
                description=reason,
            )
        return result

    def reopen(self, opportunity: Opportunity, *, user_id: uuid.UUID) -> Opportunity:
        if opportunity.status == OpportunityStatus.OPEN:
            raise ValueError("Esta oportunidade já está aberta.")
        default_stage = PipelineService(self._db).default_stage()
        opportunity.status = OpportunityStatus.OPEN
        opportunity.closed_at = None
        opportunity.stage = default_stage
        self._db.flush()
        log_activity(
            self._db,
            opportunity_id=opportunity.id,
            type_=ActivityType.SYSTEM,
            created_by=user_id,
            title="Oportunidade reaberta",
        )
        return opportunity

    def change_owner(self, opportunity: Opportunity, *, new_owner_id: uuid.UUID, changed_by: uuid.UUID) -> Opportunity:
        from app.domains.auth.models import User

        new_owner = self._db.get(User, new_owner_id)
        if new_owner is None:
            raise ValueError(f"Usuário {new_owner_id} não encontrado.")

        old_owner_id = opportunity.owner_id
        opportunity.owner_id = new_owner_id
        self._db.flush()
        log_activity(
            self._db,
            opportunity_id=opportunity.id,
            type_=ActivityType.OWNERSHIP_CHANGED,
            created_by=changed_by,
            title="Responsável alterado",
            context={"from_owner": str(old_owner_id), "to_owner": str(new_owner_id)},
        )
        return opportunity


class ContactService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        company_id: uuid.UUID,
        name: str,
        role: str | None,
        email: str | None,
        phone: str | None,
        source: str,
    ) -> Contact:
        company = self._db.get(Company, company_id)
        if company is None:
            raise LookupError(f"Company {company_id} não encontrada")

        contact = Contact(company_id=company_id, name=name, role=role, email=email, phone=phone, source=source)
        self._db.add(contact)
        self._db.flush()
        return contact

    def list_for_company(self, company_id: uuid.UUID) -> list[Contact]:
        return (
            self._db.query(Contact)
            .filter(Contact.company_id == company_id)
            .order_by(Contact.created_at.desc())
            .all()
        )

    def update(
        self,
        contact: Contact,
        *,
        name: str | None = None,
        role: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        validation_status: ContactValidationStatus | None = None,
    ) -> Contact:
        if name is not None:
            contact.name = name
        if role is not None:
            contact.role = role
        if email is not None:
            contact.email = email
        if phone is not None:
            contact.phone = phone
        if validation_status is not None:
            contact.validation_status = validation_status
        self._db.flush()
        return contact

    def delete(self, contact: Contact) -> None:
        self._db.delete(contact)
        self._db.flush()


class ActivityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        opportunity_id: uuid.UUID,
        type_: ActivityType,
        created_by: uuid.UUID,
        title: str | None = None,
        description: str | None = None,
        due_at: datetime | None = None,
    ) -> Activity:
        initial_status = ActivityStatus.OPEN if type_ == ActivityType.TASK else None
        return log_activity(
            self._db,
            opportunity_id=opportunity_id,
            type_=type_,
            created_by=created_by,
            title=title,
            description=description,
            due_at=due_at,
            status=initial_status,
        )

    def update(
        self,
        activity: Activity,
        *,
        title: str | None = None,
        description: str | None = None,
        due_at: datetime | None = None,
        completed: bool | None = None,
    ) -> Activity:
        if title is not None:
            activity.title = title
        if description is not None:
            activity.description = description
        if due_at is not None:
            activity.due_at = due_at
        if completed is not None:
            if activity.type != ActivityType.TASK:
                raise ValueError("Somente atividades do tipo TASK podem ser concluídas/reabertas.")
            activity.status = ActivityStatus.DONE if completed else ActivityStatus.OPEN
            activity.completed_at = _now() if completed else None
        self._db.flush()
        return activity

    def delete(self, activity: Activity) -> None:
        if activity.type not in _DELETABLE_ACTIVITY_TYPES:
            raise ValueError(f"Atividades do tipo '{activity.type.value}' são geradas pelo sistema e não podem ser excluídas.")
        self._db.delete(activity)
        self._db.flush()

    def timeline(self, opportunity_id: uuid.UUID, *, limit: int = 100, offset: int = 0) -> list[Activity]:
        return (
            self._db.query(Activity)
            .filter(Activity.opportunity_id == opportunity_id)
            .order_by(Activity.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def overdue_tasks_for_owner(self, owner_id: uuid.UUID) -> list[Activity]:
        return (
            self._db.query(Activity)
            .join(Opportunity, Opportunity.id == Activity.opportunity_id)
            .filter(
                Opportunity.owner_id == owner_id,
                Activity.type == ActivityType.TASK,
                Activity.status == ActivityStatus.OPEN,
                Activity.due_at.isnot(None),
                Activity.due_at < _now(),
            )
            .order_by(Activity.due_at.asc())
            .all()
        )


__all__ = [
    "PipelineService",
    "OpportunityService",
    "ContactService",
    "ActivityService",
    "OpportunityPage",
    "log_activity",
]
