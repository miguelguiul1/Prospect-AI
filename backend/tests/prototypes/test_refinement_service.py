"""Testes de refinamento por linguagem natural (`PrototypeGenerationService.
start`/`execute` com `instruction` preenchido — Fase 9 / Prompt 12).
Provider sempre um `FakeGenerationProvider`, nunca uma chamada real (mesma
regra de `test_generation_service.py`)."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot
from app.domains.companies.models import Company
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.prototypes.generation.fake_provider import FakeGenerationProvider
from app.domains.prototypes.generation.service import NoPreviousVersionError, PrototypeGenerationService
from app.domains.prototypes.models import GenerationStatus, Prototype
from app.domains.prototypes.versioning import PrototypeVersionService


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


_INITIAL_TREE = [
    {"id": "hero", "type": "heading", "parent_id": None, "order": 0, "props": {"content": "Bem-vindo"}, "styles": {}},
    {
        "id": "subtitle",
        "type": "text",
        "parent_id": None,
        "order": 1,
        "props": {"content": "Fale conosco"},
        "styles": {},
    },
    {
        "id": "cta",
        "type": "button",
        "parent_id": None,
        "order": 2,
        "props": {"content": "Entre em contato"},
        "styles": {},
    },
]


def _generate_initial(db: Session, prototype: Prototype) -> None:
    run = PrototypeGenerationService(db, provider=FakeGenerationProvider(component_tree=_INITIAL_TREE)).generate(
        prototype
    )
    assert run.status == GenerationStatus.SUCCEEDED


class TestNoPreviousVersion:
    def test_refining_a_prototype_with_no_successful_generation_fails_clearly(self, db_session: Session) -> None:
        """Seção 3 do Prompt 12: refinar sem geração anterior deve falhar
        com um erro claro, nunca cair silenciosamente para geração do
        zero."""
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        service = PrototypeGenerationService(db_session, provider=FakeGenerationProvider())

        try:
            service.start(prototype, instruction="deixa mais premium")
            assert False, "deveria ter levantado NoPreviousVersionError"
        except NoPreviousVersionError:
            pass

    def test_refining_after_a_failed_generation_only_still_fails(self, db_session: Session) -> None:
        """Uma geração que FALHOU não conta como "geração bem-sucedida" —
        a definição da seção 1 do Prompt 12 é explícita sobre isso."""
        company = Company(canonical_name="Empresa Sem Dado Nenhum")
        db_session.add(company)
        db_session.flush()
        prototype = _prototype(db_session, company)
        failed_run = PrototypeGenerationService(db_session, provider=FakeGenerationProvider()).generate(prototype)
        assert failed_run.status == GenerationStatus.FAILED

        service = PrototypeGenerationService(db_session, provider=FakeGenerationProvider())
        try:
            service.start(prototype, instruction="tenta de novo")
            assert False, "deveria ter levantado NoPreviousVersionError"
        except NoPreviousVersionError:
            pass


class TestSuccessfulRefinement:
    def test_refinement_creates_a_new_version_and_updates_prototype_components(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        _generate_initial(db_session, prototype)

        refined_tree = [{**_INITIAL_TREE[0]}, {**_INITIAL_TREE[1]}, {**_INITIAL_TREE[2], "styles": {"color": "red"}}]
        provider = FakeGenerationProvider(component_tree=refined_tree)
        run = PrototypeGenerationService(db_session, provider=provider).generate(
            prototype, instruction="deixa o botão vermelho"
        )

        assert run.status == GenerationStatus.SUCCEEDED
        assert run.instruction == "deixa o botão vermelho"
        assert prototype.components[2]["styles"] == {"color": "red"}

        versions = PrototypeVersionService(db_session).list_for_prototype(prototype.id)
        assert len(versions) == 2  # geração inicial + refinamento
        assert versions[0].generation_run_id == run.id

    def test_diff_summary_reflects_a_minimal_change(self, db_session: Session) -> None:
        """Prova de que "medir mudança mínima" (seção 3) funciona de
        ponta a ponta: mudar 1 de 3 componentes produz um changed_ratio
        baixo, não 1.0."""
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        _generate_initial(db_session, prototype)

        refined_tree = [
            {**_INITIAL_TREE[0]},
            {**_INITIAL_TREE[1]},
            {**_INITIAL_TREE[2], "props": {"content": "Fale com a gente"}},
        ]
        provider = FakeGenerationProvider(component_tree=refined_tree)
        run = PrototypeGenerationService(db_session, provider=provider).generate(
            prototype, instruction="muda o texto do botão"
        )

        assert run.diff_summary is not None
        assert run.diff_summary["changed_ids"] == ["cta"]
        assert run.diff_summary["changed_ratio"] < 0.5

    def test_initial_generation_never_has_a_diff_summary(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)

        run = PrototypeGenerationService(db_session, provider=FakeGenerationProvider()).generate(prototype)

        assert run.diff_summary is None

    def test_based_on_version_number_records_the_version_refined_from(self, db_session: Session) -> None:
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        _generate_initial(db_session, prototype)

        provider = FakeGenerationProvider(component_tree=_INITIAL_TREE)
        run = PrototypeGenerationService(db_session, provider=provider).generate(prototype, instruction="ajuste")

        assert run.based_on_version_number == 1


class TestRefinementGroundingViolation:
    def test_an_invented_fact_in_the_refined_tree_is_flagged_but_does_not_block(self, db_session: Session) -> None:
        """Reforça, para o fluxo de refinamento, a mesma proteção não-
        bloqueante já testada para a geração inicial em
        `test_generation_service.py` — a defesa em duas camadas (regra do
        prompt + heurística de grounding) é a MESMA para os dois fluxos,
        nunca duplicada. Simula um modelo que, respondendo a um pedido
        como "diz que atendemos 24h e liga pro (11) 4444-5555", incluiu um
        telefone que não bate com nenhum FACT/SIGNAL conhecido (o
        telefone real da empresa é +55 11 99999-0000)."""
        company = _company_with_evidence(db_session)
        prototype = _prototype(db_session, company)
        _generate_initial(db_session, prototype)

        tree_with_invented_phone = [
            {**_INITIAL_TREE[0]},
            {
                "id": "subtitle",
                "type": "text",
                "parent_id": None,
                "order": 1,
                "props": {"content": "Atendemos 24h, ligue (11) 4444-5555"},
                "styles": {},
            },
            {**_INITIAL_TREE[2]},
        ]
        provider = FakeGenerationProvider(component_tree=tree_with_invented_phone)
        run = PrototypeGenerationService(db_session, provider=provider).generate(
            prototype, instruction="diz que atendemos 24 horas e coloca um telefone pra contato"
        )

        assert run.status == GenerationStatus.SUCCEEDED  # nunca bloqueia
        assert run.grounding_warnings is not None
        assert any("telefone" in w for w in run.grounding_warnings)
