"""Testes de serviço do domínio `crm` (Fase 7) — direto contra o banco de
teste (`db_session`), sem passar pela API HTTP."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.models import User
from app.domains.companies.models import Company
from app.domains.crm.enums import ActivityType, OpportunityPriority, OpportunityStatus
from app.domains.crm.models import Activity, Opportunity
from app.domains.crm.service import ActivityService, ContactService, OpportunityService, PipelineService


def _user(db: Session, email: str = "dono@example.com") -> User:
    user = User(email=email, name="Dono Teste", password_hash="x")
    db.add(user)
    db.flush()
    return user


def _company(db: Session, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    return company


class TestPipelineService:
    def test_default_stage_is_the_first_by_order(self, db_session: Session) -> None:
        stage = PipelineService(db_session).default_stage()
        assert stage.key == "new"
        assert stage.order == 1

    def test_terminal_stages_are_won_and_lost(self, db_session: Session) -> None:
        service = PipelineService(db_session)
        assert service.terminal_stage(won=True).key == "won"
        assert service.terminal_stage(won=False).key == "lost"

    def test_all_eight_default_stages_exist_in_order(self, db_session: Session) -> None:
        stages = PipelineService(db_session).list_stages()
        assert [s.key for s in stages] == [
            "new", "qualified", "contacted", "meeting", "proposal", "negotiation", "won", "lost",
        ]


class TestOpportunityCreateOrGet:
    def test_creates_a_new_open_opportunity(self, db_session: Session) -> None:
        user = _user(db_session)
        company = _company(db_session)
        opportunity, created = OpportunityService(db_session).create_or_get(
            company_id=company.id, owner_id=user.id, priority=OpportunityPriority.MEDIUM
        )
        assert created is True
        assert opportunity.status == OpportunityStatus.OPEN
        assert opportunity.stage.key == "new"
        assert opportunity.owner_id == user.id

    def test_second_call_for_the_same_company_is_idempotent(self, db_session: Session) -> None:
        user = _user(db_session)
        company = _company(db_session)
        service = OpportunityService(db_session)

        first, created_first = service.create_or_get(
            company_id=company.id, owner_id=user.id, priority=OpportunityPriority.MEDIUM
        )
        second, created_second = service.create_or_get(
            company_id=company.id, owner_id=user.id, priority=OpportunityPriority.HIGH
        )

        assert created_first is True
        assert created_second is False
        assert first.id == second.id
        assert second.priority == OpportunityPriority.MEDIUM  # não foi sobrescrita pela segunda chamada

    def test_creating_a_system_activity_on_creation(self, db_session: Session) -> None:
        user = _user(db_session)
        company = _company(db_session)
        opportunity, _ = OpportunityService(db_session).create_or_get(
            company_id=company.id, owner_id=user.id, priority=OpportunityPriority.MEDIUM
        )
        activities = db_session.query(Activity).filter(Activity.opportunity_id == opportunity.id).all()
        assert len(activities) == 1
        assert activities[0].type == ActivityType.SYSTEM

    def test_unknown_company_raises_lookup_error(self, db_session: Session) -> None:
        user = _user(db_session)
        with pytest.raises(LookupError):
            OpportunityService(db_session).create_or_get(
                company_id=uuid.uuid4(), owner_id=user.id, priority=OpportunityPriority.MEDIUM
            )

    def test_database_enforces_at_most_one_open_opportunity_per_company(self, db_session: Session) -> None:
        """Prova estrutural do índice único parcial (Prompt 11, seção 24):
        mesmo inserindo diretamente via ORM (contornando o serviço), o banco
        rejeita uma segunda Opportunity OPEN para a mesma empresa."""
        user = _user(db_session)
        company = _company(db_session)
        stage = PipelineService(db_session).default_stage()

        db_session.add(Opportunity(company_id=company.id, owner_id=user.id, stage_id=stage.id, status=OpportunityStatus.OPEN))
        db_session.flush()

        db_session.add(Opportunity(company_id=company.id, owner_id=user.id, stage_id=stage.id, status=OpportunityStatus.OPEN))
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestOpportunityStageAndStatus:
    def _open_opportunity(self, db: Session) -> tuple[Opportunity, User]:
        user = _user(db)
        company = _company(db)
        opportunity, _ = OpportunityService(db).create_or_get(
            company_id=company.id, owner_id=user.id, priority=OpportunityPriority.MEDIUM
        )
        return opportunity, user

    def test_change_stage_updates_stage_and_logs_activity(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        OpportunityService(db_session).change_stage(opportunity, stage_key="qualified", user_id=user.id)

        assert opportunity.stage.key == "qualified"
        assert opportunity.status == OpportunityStatus.OPEN
        stage_changes = (
            db_session.query(Activity)
            .filter(Activity.opportunity_id == opportunity.id, Activity.type == ActivityType.STAGE_CHANGE)
            .all()
        )
        assert len(stage_changes) == 1
        assert stage_changes[0].context == {"from_stage": "new", "to_stage": "qualified"}

    def test_moving_to_a_won_stage_closes_the_opportunity(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        OpportunityService(db_session).change_stage(opportunity, stage_key="won", user_id=user.id)

        assert opportunity.status == OpportunityStatus.WON
        assert opportunity.closed_at is not None

    def test_invalid_stage_key_raises_value_error(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        with pytest.raises(ValueError):
            OpportunityService(db_session).change_stage(opportunity, stage_key="nao-existe", user_id=user.id)

    def test_cannot_change_stage_of_a_closed_opportunity(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        OpportunityService(db_session).close(opportunity, outcome="lost", reason=None, user_id=user.id)
        with pytest.raises(ValueError):
            OpportunityService(db_session).change_stage(opportunity, stage_key="qualified", user_id=user.id)

    def test_close_with_reason_logs_a_note(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        OpportunityService(db_session).close(opportunity, outcome="lost", reason="Fechou com concorrente", user_id=user.id)

        notes = (
            db_session.query(Activity)
            .filter(Activity.opportunity_id == opportunity.id, Activity.type == ActivityType.NOTE)
            .all()
        )
        assert len(notes) == 1
        assert notes[0].description == "Fechou com concorrente"

    def test_cannot_close_an_already_closed_opportunity(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        OpportunityService(db_session).close(opportunity, outcome="won", reason=None, user_id=user.id)
        with pytest.raises(ValueError):
            OpportunityService(db_session).close(opportunity, outcome="lost", reason=None, user_id=user.id)

    def test_reopen_resets_status_and_stage(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        OpportunityService(db_session).close(opportunity, outcome="lost", reason=None, user_id=user.id)

        OpportunityService(db_session).reopen(opportunity, user_id=user.id)

        assert opportunity.status == OpportunityStatus.OPEN
        assert opportunity.closed_at is None
        assert opportunity.stage.key == "new"

    def test_cannot_reopen_an_already_open_opportunity(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        with pytest.raises(ValueError):
            OpportunityService(db_session).reopen(opportunity, user_id=user.id)

    def test_change_owner_updates_owner_and_logs_activity(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        new_owner = _user(db_session, email="novo-dono@example.com")

        OpportunityService(db_session).change_owner(opportunity, new_owner_id=new_owner.id, changed_by=user.id)

        assert opportunity.owner_id == new_owner.id
        ownership_changes = (
            db_session.query(Activity)
            .filter(Activity.opportunity_id == opportunity.id, Activity.type == ActivityType.OWNERSHIP_CHANGED)
            .all()
        )
        assert len(ownership_changes) == 1

    def test_change_owner_to_unknown_user_raises_value_error(self, db_session: Session) -> None:
        opportunity, user = self._open_opportunity(db_session)
        with pytest.raises(ValueError):
            OpportunityService(db_session).change_owner(opportunity, new_owner_id=uuid.uuid4(), changed_by=user.id)


class TestContactService:
    def test_create_and_list_contacts_for_company(self, db_session: Session) -> None:
        company = _company(db_session)
        service = ContactService(db_session)
        service.create(company_id=company.id, name="Fulano", role="Gerente", email=None, phone=None, source="manual")

        contacts = service.list_for_company(company.id)
        assert len(contacts) == 1
        assert contacts[0].name == "Fulano"
        assert contacts[0].source == "manual"

    def test_create_for_unknown_company_raises_lookup_error(self, db_session: Session) -> None:
        with pytest.raises(LookupError):
            ContactService(db_session).create(
                company_id=uuid.uuid4(), name="X", role=None, email=None, phone=None, source="manual"
            )

    def test_update_contact_fields(self, db_session: Session) -> None:
        company = _company(db_session)
        contact = ContactService(db_session).create(
            company_id=company.id, name="Fulano", role=None, email=None, phone=None, source="manual"
        )
        from app.domains.crm.enums import ContactValidationStatus

        ContactService(db_session).update(contact, validation_status=ContactValidationStatus.VERIFIED)
        assert contact.validation_status == ContactValidationStatus.VERIFIED

    def test_delete_contact(self, db_session: Session) -> None:
        company = _company(db_session)
        contact = ContactService(db_session).create(
            company_id=company.id, name="Fulano", role=None, email=None, phone=None, source="manual"
        )
        ContactService(db_session).delete(contact)
        assert ContactService(db_session).list_for_company(company.id) == []


class TestActivityService:
    def _opportunity(self, db: Session) -> tuple[Opportunity, User]:
        user = _user(db)
        company = _company(db)
        opportunity, _ = OpportunityService(db).create_or_get(
            company_id=company.id, owner_id=user.id, priority=OpportunityPriority.MEDIUM
        )
        return opportunity, user

    def test_create_note(self, db_session: Session) -> None:
        opportunity, user = self._opportunity(db_session)
        activity = ActivityService(db_session).create(
            opportunity_id=opportunity.id, type_=ActivityType.NOTE, created_by=user.id, description="Uma nota qualquer"
        )
        assert activity.status is None

    def test_create_task_starts_open(self, db_session: Session) -> None:
        opportunity, user = self._opportunity(db_session)
        activity = ActivityService(db_session).create(
            opportunity_id=opportunity.id, type_=ActivityType.TASK, created_by=user.id, title="Ligar amanhã"
        )
        from app.domains.crm.enums import ActivityStatus

        assert activity.status == ActivityStatus.OPEN

    def test_completing_a_task_sets_done_and_completed_at(self, db_session: Session) -> None:
        opportunity, user = self._opportunity(db_session)
        activity = ActivityService(db_session).create(
            opportunity_id=opportunity.id, type_=ActivityType.TASK, created_by=user.id, title="Ligar"
        )
        ActivityService(db_session).update(activity, completed=True)

        from app.domains.crm.enums import ActivityStatus

        assert activity.status == ActivityStatus.DONE
        assert activity.completed_at is not None

    def test_reopening_a_task_clears_completed_at(self, db_session: Session) -> None:
        opportunity, user = self._opportunity(db_session)
        activity = ActivityService(db_session).create(
            opportunity_id=opportunity.id, type_=ActivityType.TASK, created_by=user.id, title="Ligar"
        )
        ActivityService(db_session).update(activity, completed=True)
        ActivityService(db_session).update(activity, completed=False)

        from app.domains.crm.enums import ActivityStatus

        assert activity.status == ActivityStatus.OPEN
        assert activity.completed_at is None

    def test_completing_a_non_task_activity_raises_value_error(self, db_session: Session) -> None:
        opportunity, user = self._opportunity(db_session)
        activity = ActivityService(db_session).create(
            opportunity_id=opportunity.id, type_=ActivityType.NOTE, created_by=user.id, description="Nota"
        )
        with pytest.raises(ValueError):
            ActivityService(db_session).update(activity, completed=True)

    def test_deleting_a_system_generated_activity_is_rejected(self, db_session: Session) -> None:
        opportunity, user = self._opportunity(db_session)
        system_activity = (
            db_session.query(Activity)
            .filter(Activity.opportunity_id == opportunity.id, Activity.type == ActivityType.SYSTEM)
            .one()
        )
        with pytest.raises(ValueError):
            ActivityService(db_session).delete(system_activity)

    def test_deleting_a_note_is_allowed(self, db_session: Session) -> None:
        opportunity, user = self._opportunity(db_session)
        activity = ActivityService(db_session).create(
            opportunity_id=opportunity.id, type_=ActivityType.NOTE, created_by=user.id, description="Nota"
        )
        ActivityService(db_session).delete(activity)
        assert db_session.get(Activity, activity.id) is None

    def test_timeline_is_ordered_most_recent_first(self, db_session: Session) -> None:
        opportunity, user = self._opportunity(db_session)
        ActivityService(db_session).create(opportunity_id=opportunity.id, type_=ActivityType.NOTE, created_by=user.id, description="primeira")
        ActivityService(db_session).create(opportunity_id=opportunity.id, type_=ActivityType.NOTE, created_by=user.id, description="segunda")

        timeline = ActivityService(db_session).timeline(opportunity.id)
        # A "criada" (SYSTEM) + as duas notas = 3 no total, mais recente primeiro.
        assert len(timeline) == 3
        assert timeline[0].description == "segunda"

    def test_overdue_tasks_only_include_open_tasks_past_due_date(self, db_session: Session) -> None:
        from datetime import datetime, timedelta, timezone

        opportunity, user = self._opportunity(db_session)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        overdue = ActivityService(db_session).create(
            opportunity_id=opportunity.id, type_=ActivityType.TASK, created_by=user.id, title="Atrasada", due_at=past
        )
        ActivityService(db_session).create(
            opportunity_id=opportunity.id, type_=ActivityType.TASK, created_by=user.id, title="Futura", due_at=future
        )
        done = ActivityService(db_session).create(
            opportunity_id=opportunity.id, type_=ActivityType.TASK, created_by=user.id, title="Concluída", due_at=past
        )
        ActivityService(db_session).update(done, completed=True)

        overdue_tasks = ActivityService(db_session).overdue_tasks_for_owner(user.id)
        assert [t.id for t in overdue_tasks] == [overdue.id]
