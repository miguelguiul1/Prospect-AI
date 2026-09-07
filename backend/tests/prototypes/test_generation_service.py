"""Testes de `PrototypeGenerationService` (Fase 9 / Prompt 11) — provider
de IA sempre um `FakeGenerationProvider` injetado, nunca uma chamada
real (mesma regra do Sales Brief/Outreach)."""
from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot
from app.domains.briefing.providers.errors import ProviderTimeoutError, ProviderUnavailableError
from app.domains.companies.models import Company
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.prototypes.generation.fake_provider import DEFAULT_COMPONENT_TREE, FakeGenerationProvider
from app.domains.prototypes.generation.service import GenerationInProgressError, PrototypeGenerationService
from app.domains.prototypes.models import GenerationRun, GenerationStatus, Prototype


def _company_with_evidence(db: Session, name: str = "Padaria Central") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    db.add(
        Evidence(
            company_id=company.id,
            field="phone",
            value="+55 11 99999-0000",
            state=DataState.CONFIRMED,
            source="google_places",
            method=EvidenceMethod.STRUCTURED_FIELD,
            confidence=ConfidenceLevel.HIGH,
        )
    )
    db.add(AuditSnapshot(company_id=company.id, run_id=uuid.uuid4(), status=AuditStatus.COMPLETED))
    db.flush()
    return company


def _prototype(db: Session, company: Company) -> Prototype:
    prototype = Prototype(name="Site de Teste", company_id=company.id, components=[], settings={})
    db.add(prototype)
    db.flush()
    return prototype


class TestSuccessfulGeneration:
    def test_generates_and_persists_the_component_tree(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        provider = FakeGenerationProvider()

        run = PrototypeGenerationService(db_session, provider=provider).generate(prototype)

        assert run.status == GenerationStatus.SUCCEEDED
        assert run.provider == "fake"
        assert run.input_tokens == 120
        assert run.output_tokens == 340
        assert len(prototype.components) == len(DEFAULT_COMPONENT_TREE)

    def test_persists_a_context_snapshot_linked_to_the_run(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)

        run = PrototypeGenerationService(db_session, provider=FakeGenerationProvider()).generate(prototype)

        assert run.context_snapshot is not None
        assert run.context_snapshot.context["fields"]["company_name"]["value"] == "Padaria Central"

    def test_no_grounding_warnings_for_generic_copy(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)

        run = PrototypeGenerationService(db_session, provider=FakeGenerationProvider()).generate(prototype)

        assert run.grounding_warnings is None

    def test_grounding_warning_is_persisted_but_generation_still_succeeds(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)  # telefone conhecido: +55 11 99999-0000
        prototype = _prototype(db_session, company)
        tree = [
            {
                "id": "t",
                "type": "text",
                "parent_id": None,
                "order": 0,
                "props": {"content": "Ligue para (21) 3333-4444 agora"},  # telefone DIFERENTE do conhecido
                "styles": {},
            }
        ]
        provider = FakeGenerationProvider(component_tree=tree)

        run = PrototypeGenerationService(db_session, provider=provider).generate(prototype)

        assert run.status == GenerationStatus.SUCCEEDED
        assert run.grounding_warnings is not None
        assert len(run.grounding_warnings) == 1


class TestGenerationFailures:
    def test_malformed_json_never_updates_the_prototype(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        provider = FakeGenerationProvider(response_text="isto não é json")

        run = PrototypeGenerationService(db_session, provider=provider).generate(prototype)

        assert run.status == GenerationStatus.FAILED
        assert run.error_code == "JSONDecodeError"
        assert prototype.components == []

    def test_missing_components_key_fails_cleanly(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        provider = FakeGenerationProvider(response_text=json.dumps({"wrong_key": []}))

        run = PrototypeGenerationService(db_session, provider=provider).generate(prototype)

        assert run.status == GenerationStatus.FAILED
        assert run.error_code == "KeyError"

    def test_provider_unavailable_never_persists_a_fake_tree(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        provider = FakeGenerationProvider(error=ProviderUnavailableError("sem chave"))

        run = PrototypeGenerationService(db_session, provider=provider).generate(prototype)

        assert run.status == GenerationStatus.FAILED
        assert run.error_code == "ProviderUnavailableError"
        assert prototype.components == []

    def test_provider_timeout_fails_cleanly(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        provider = FakeGenerationProvider(error=ProviderTimeoutError("timeout"))

        run = PrototypeGenerationService(db_session, provider=provider).generate(prototype)

        assert run.status == GenerationStatus.FAILED
        assert run.error_code == "ProviderTimeoutError"

    def test_unsafe_url_in_generated_tree_fails_and_never_persists(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        tree = [
            {
                "id": "img",
                "type": "image",
                "parent_id": None,
                "order": 0,
                "props": {"src": "javascript:alert(1)"},
                "styles": {},
            }
        ]
        provider = FakeGenerationProvider(component_tree=tree)

        run = PrototypeGenerationService(db_session, provider=provider).generate(prototype)

        assert run.status == GenerationStatus.FAILED
        assert run.error_code == "UnsafeGeneratedContentError"
        assert prototype.components == []

    def test_insufficient_context_fails_before_calling_the_provider(self, db_session: Session) -> None:
        company = Company(canonical_name="Empresa Sem Dado Nenhum")
        db_session.add(company)
        db_session.flush()
        prototype = _prototype(db_session, company)
        provider = FakeGenerationProvider()

        run = PrototypeGenerationService(db_session, provider=provider).generate(prototype)

        assert run.status == GenerationStatus.FAILED
        assert run.error_code == "InsufficientContextError"
        assert provider.last_call is None  # nunca chamou o provider


class TestStartAndExecuteSeparately:
    """`start()` cria o GenerationRun em PENDING sem tocar no provider —
    é o que a rota HTTP devolve imediatamente (seção 5 do Prompt 11:
    GET /generations/{id} precisa de um id que já existe antes da
    geração real terminar)."""

    def test_start_creates_a_pending_run_without_calling_the_provider(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        provider = FakeGenerationProvider()

        run = PrototypeGenerationService(db_session, provider=provider).start(prototype)

        assert run.status == GenerationStatus.PENDING
        assert provider.last_call is None

    def test_execute_transitions_the_same_run_to_succeeded(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        provider = FakeGenerationProvider()
        service = PrototypeGenerationService(db_session, provider=provider)

        run = service.start(prototype)
        run_id_before = run.id
        result = service.execute(run)

        assert result.id == run_id_before  # mesma linha, nunca uma segunda
        assert result.status == GenerationStatus.SUCCEEDED
        assert provider.last_call is not None

    def test_start_itself_is_blocked_by_an_existing_pending_run(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        service = PrototypeGenerationService(db_session, provider=FakeGenerationProvider())
        service.start(prototype)

        import pytest

        with pytest.raises(GenerationInProgressError):
            service.start(prototype)


class TestOneGenerationAtATime:
    def test_a_second_generation_is_rejected_while_one_is_pending(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        db_session.add(
            GenerationRun(
                prototype_id=prototype.id,
                company_id=company.id,
                status=GenerationStatus.PENDING,
                prompt_version="v1",
                context_version="v1",
            )
        )
        db_session.flush()

        import pytest

        with pytest.raises(GenerationInProgressError):
            PrototypeGenerationService(db_session, provider=FakeGenerationProvider()).generate(prototype)

    def test_generation_is_allowed_again_after_the_previous_one_completed(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        db_session.add(
            GenerationRun(
                prototype_id=prototype.id,
                company_id=company.id,
                status=GenerationStatus.SUCCEEDED,
                prompt_version="v1",
                context_version="v1",
            )
        )
        db_session.flush()

        run = PrototypeGenerationService(db_session, provider=FakeGenerationProvider()).generate(prototype)

        assert run.status == GenerationStatus.SUCCEEDED
