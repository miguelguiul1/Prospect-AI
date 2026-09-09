"""API HTTP do Prototype Builder (Fase 6; autenticação + vínculo com
Company no Prompt 10).

Toda rota depende de `get_current_user` — não há mais nenhum endpoint
público neste router além do catálogo de tipos (que não expõe dado de
nenhum usuário). Leitura/escrita de um `Prototype` específico sempre passa
por `get_accessible_prototype_or_404`, nunca confia em nada vindo do
payload do cliente para decidir acesso (mesmo padrão do resto do CRM,
Fase 7).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import check_and_increment
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.prototypes.authorization import get_accessible_prototype_or_404
from app.domains.prototypes.export import build_export_zip, export_filename
from app.domains.prototypes.generation.service import (
    GenerationInProgressError,
    NoPreviousVersionError,
    PrototypeGenerationService,
)
from app.domains.prototypes.jobs import enqueue_or_run_prototype_generation
from app.domains.prototypes.models import GenerationRun, GenerationStatus, PrototypeVersion
from app.domains.prototypes.schemas import (
    COMPONENT_CATEGORIES,
    COMPONENT_TYPES,
    PrototypeCreateRequest,
    PrototypeUpdateRequest,
)
from app.domains.prototypes.service import PrototypeService
from app.domains.prototypes.versioning import PrototypeVersionService

router = APIRouter(prefix="/api/prototypes", tags=["prototypes"])

_VERSION_DESCRIPTION_MAX_LENGTH = 140


def _version_description(version: PrototypeVersion) -> str:
    """Descrição curta para exibição na lista de versões (seção 6 do
    Prompt 12) — nunca armazenada, sempre derivada na hora a partir de
    qual dos três caminhos criou esta versão (ver docstring de
    `PrototypeVersion`): restauração, geração/refinamento por IA, ou
    edição manual (só possível quando nem `restored_from_version_number`
    nem `generation_run_id` estão preenchidos)."""
    if version.restored_from_version_number is not None:
        return f"Restaurado da versão {version.restored_from_version_number}"
    if version.generation_run is not None and version.generation_run.instruction:
        text = version.generation_run.instruction.strip()
        if len(text) > _VERSION_DESCRIPTION_MAX_LENGTH:
            text = text[: _VERSION_DESCRIPTION_MAX_LENGTH - 1] + "…"
        return text
    if version.generation_run is not None:
        return "Geração inicial por IA"
    return "Editado manualmente no Builder"


class PrototypeResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    company_id: uuid.UUID | None
    components: list[dict]
    settings: dict
    created_at: datetime
    updated_at: datetime


class PrototypeListItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    company_id: uuid.UUID | None
    component_count: int
    created_at: datetime
    updated_at: datetime


class PrototypeListResponse(BaseModel):
    items: list[PrototypeListItemResponse]
    total: int
    limit: int
    offset: int


class ComponentTypeResponse(BaseModel):
    type: str
    category: str


class GenerationRunResponse(BaseModel):
    id: uuid.UUID
    prototype_id: uuid.UUID
    company_id: uuid.UUID
    status: GenerationStatus
    provider: str | None
    model: str | None
    prompt_version: str
    context_version: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: float | None
    error_code: str | None
    error_message: str | None
    grounding_warnings: list[str] | None
    # Três campos novos do Prompt 12 — `None` para uma geração inicial,
    # preenchidos só para um refinamento (ver `GenerationRun` em
    # `app.domains.prototypes.models`).
    instruction: str | None
    based_on_version_number: int | None
    diff_summary: dict | None
    created_at: datetime
    completed_at: datetime | None
    execution_mode: str | None = None


class RefineRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=4000)


class PrototypeVersionListItemResponse(BaseModel):
    id: uuid.UUID
    version_number: int
    component_count: int
    description: str
    created_at: datetime


class PrototypeVersionDetailResponse(BaseModel):
    id: uuid.UUID
    version_number: int
    components: list[dict]
    description: str
    instruction: str | None
    restored_from_version_number: int | None
    created_at: datetime


def _version_to_list_item(version: PrototypeVersion) -> PrototypeVersionListItemResponse:
    return PrototypeVersionListItemResponse(
        id=version.id,
        version_number=version.version_number,
        component_count=len(version.components),
        description=_version_description(version),
        created_at=version.created_at,
    )


def _version_to_detail(version: PrototypeVersion) -> PrototypeVersionDetailResponse:
    return PrototypeVersionDetailResponse(
        id=version.id,
        version_number=version.version_number,
        components=version.components,
        description=_version_description(version),
        instruction=version.generation_run.instruction if version.generation_run is not None else None,
        restored_from_version_number=version.restored_from_version_number,
        created_at=version.created_at,
    )


class RefinementHistoryItemResponse(BaseModel):
    """Uma entrada do "chat" de refinamento (Prompt 13, seção 2) — um
    `GenerationRun` com `instruction` preenchido (nunca a geração
    inicial, que tem `instruction=None`). Nunca uma tabela nova: é uma
    leitura derivada de `GenerationRun` + `PrototypeVersion` que já
    existiam desde o Prompt 12, montada só para exibição — decisão
    "histórico só de apresentação" documentada em
    `docs/prototype-refinement.md`."""

    id: uuid.UUID
    instruction: str
    status: GenerationStatus
    error_message: str | None
    grounding_warnings: list[str] | None
    diff_summary: dict | None
    version_id: uuid.UUID | None
    version_number: int | None
    created_at: datetime
    completed_at: datetime | None


def _refinement_to_response(run: GenerationRun) -> RefinementHistoryItemResponse:
    assert run.instruction is not None  # garantido pelo filtro da query em list_refinements
    version = run.version
    return RefinementHistoryItemResponse(
        id=run.id,
        instruction=run.instruction,
        status=run.status,
        error_message=run.error_message,
        grounding_warnings=run.grounding_warnings,
        diff_summary=run.diff_summary,
        version_id=version.id if version is not None else None,
        version_number=version.version_number if version is not None else None,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _generation_to_response(run: GenerationRun, *, execution_mode: str | None = None) -> GenerationRunResponse:
    return GenerationRunResponse(
        id=run.id,
        prototype_id=run.prototype_id,
        company_id=run.company_id,
        status=run.status,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        context_version=run.context_version,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        duration_ms=run.duration_ms,
        instruction=run.instruction,
        based_on_version_number=run.based_on_version_number,
        diff_summary=run.diff_summary,
        error_code=run.error_code,
        error_message=run.error_message,
        grounding_warnings=run.grounding_warnings,
        created_at=run.created_at,
        completed_at=run.completed_at,
        execution_mode=execution_mode,
    )


def _to_response(prototype) -> PrototypeResponse:
    return PrototypeResponse(
        id=prototype.id,
        name=prototype.name,
        description=prototype.description,
        company_id=prototype.company_id,
        components=prototype.components,
        settings=prototype.settings,
        created_at=prototype.created_at,
        updated_at=prototype.updated_at,
    )


@router.get("/meta/component-types", response_model=list[ComponentTypeResponse])
def get_component_types() -> list[ComponentTypeResponse]:
    """Catálogo de tipos de componente aceitos — a mesma fonte de verdade
    usada para validar `POST`/`PUT` (`app.domains.prototypes.schemas.
    COMPONENT_TYPES`), exposta para o frontend nunca precisar hardcodar a
    lista de forma divergente do backend. Sem dado de usuário — não exige
    autenticação (mesmo espírito de `GET /api/crm/pipeline/stages`, que
    também é um catálogo estático)."""
    return [
        ComponentTypeResponse(type=t, category=COMPONENT_CATEGORIES.get(t, "layout"))
        for t in sorted(COMPONENT_TYPES)
    ]


@router.post("", response_model=PrototypeResponse, status_code=status.HTTP_201_CREATED)
def create_prototype(
    payload: PrototypeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrototypeResponse:
    service = PrototypeService(db)
    try:
        prototype = service.create(
            name=payload.name,
            description=payload.description,
            company_id=payload.company_id,
            user_id=current_user.id,
        )
    except LookupError as exc:
        raise AppError(str(exc), code="company_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc
    except PermissionError as exc:
        # 404, não 403 — mesmo motivo documentado em
        # app.domains.prototypes.authorization: não vazar existência.
        raise AppError(str(exc), code="company_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc

    db.commit()
    db.refresh(prototype)
    return _to_response(prototype)


@router.get("", response_model=PrototypeListResponse)
def list_prototypes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PrototypeListResponse:
    service = PrototypeService(db)
    page = service.list_for_user(user_id=current_user.id, limit=limit, offset=offset)
    return PrototypeListResponse(
        items=[
            PrototypeListItemResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                company_id=p.company_id,
                component_count=len(p.components),
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{prototype_id}", response_model=PrototypeResponse)
def get_prototype(
    prototype_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrototypeResponse:
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)
    return _to_response(prototype)


@router.put("/{prototype_id}", response_model=PrototypeResponse)
def update_prototype(
    prototype_id: uuid.UUID,
    payload: PrototypeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrototypeResponse:
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)
    service = PrototypeService(db)
    try:
        prototype = service.update(
            prototype,
            name=payload.name,
            description=payload.description,
            components=payload.components,
            settings=payload.settings,
        )
    except (ValueError, ValidationError) as exc:
        raise AppError(
            f"Árvore de componentes inválida: {exc}",
            code="invalid_component_tree",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc

    db.commit()
    db.refresh(prototype)
    return _to_response(prototype)


@router.delete("/{prototype_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prototype(
    prototype_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)
    PrototypeService(db).delete(prototype)
    db.commit()


def _check_prototype_generation_rate_limit(prototype_id: uuid.UUID, settings: Settings) -> bool:
    """Mesma chave para `/generate` e `/refine` (Prompt 12, seção 5: um
    refinamento também é uma chamada de IA, então conta para o mesmo
    limite diário — nunca um balde separado que permitiria dobrar o custo
    máximo por dia só chamando os dois endpoints). Extraído para cá para
    que os dois pontos de chamada nunca possam divergir na formatação da
    chave por acidente."""
    return check_and_increment(
        f"ratelimit:prototype_generation:{prototype_id}:{datetime.now(timezone.utc).date().isoformat()}",
        max_attempts=settings.prototype_generation_rate_limit_max_per_day,
        window_seconds=24 * 60 * 60,
        on_unavailable="fail_closed",
    )


@router.post(
    "/{prototype_id}/generate", response_model=GenerationRunResponse, status_code=status.HTTP_202_ACCEPTED
)
def generate_prototype(
    prototype_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> GenerationRunResponse:
    """Dispara a geração por IA da árvore de componentes (Fase 9 /
    Prompt 11). Mesma autorização de qualquer outra rota de `Prototype`
    (só quem tem `Opportunity` para a empresa). Rate limit por
    `prototype_id` (seção 6 do Prompt 11 — nunca por usuário/empresa aqui,
    porque o limite é especificamente "evitar um loop de regeneração
    acidental NESTE protótipo"), política `fail_closed` (mesmo motivo de
    Sales Brief/Outreach: custo financeiro direto). Refinamentos (`POST
    /refine`, Prompt 12) contam para o MESMO balde diário — ver
    `_check_prototype_generation_rate_limit` abaixo."""
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)

    allowed = _check_prototype_generation_rate_limit(prototype_id, settings)
    if not allowed:
        raise AppError(
            "Limite diário de gerações atingido para este protótipo.",
            code="prototype_generation_rate_limited",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    service = PrototypeGenerationService(db)
    try:
        run = service.start(prototype)
    except GenerationInProgressError as exc:
        raise AppError(str(exc), code="generation_in_progress", status_code=status.HTTP_409_CONFLICT) from exc

    execution_mode = enqueue_or_run_prototype_generation(run.id, db=db)
    db.commit()
    db.refresh(run)

    return _generation_to_response(run, execution_mode=execution_mode)


@router.get("/{prototype_id}/generations/{generation_id}", response_model=GenerationRunResponse)
def get_generation(
    prototype_id: uuid.UUID,
    generation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerationRunResponse:
    get_accessible_prototype_or_404(db, prototype_id, current_user)

    run = PrototypeGenerationService(db).get(prototype_id, generation_id)
    if run is None:
        raise AppError(
            f"Geração {generation_id} não encontrada para o protótipo {prototype_id}.",
            code="generation_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _generation_to_response(run)


@router.post(
    "/{prototype_id}/refine", response_model=GenerationRunResponse, status_code=status.HTTP_202_ACCEPTED
)
def refine_prototype(
    prototype_id: uuid.UUID,
    payload: RefineRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> GenerationRunResponse:
    """Refinamento por linguagem natural (Fase 9 / Prompt 12) — mesmo
    contrato de resposta e mesmo pipeline de `POST /generate` (mesma
    validação, mesmo tratamento de falha), só o prompt e o
    `GenerationRun.instruction` diferem. Mesma autorização, mesmo rate
    limit COMPARTILHADO (`_check_prototype_generation_rate_limit`), e
    mesmo limite de "uma geração em andamento por vez" (`start()` levanta
    `GenerationInProgressError` para os dois fluxos igualmente)."""
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)

    allowed = _check_prototype_generation_rate_limit(prototype_id, settings)
    if not allowed:
        raise AppError(
            "Limite diário de gerações atingido para este protótipo.",
            code="prototype_generation_rate_limited",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    service = PrototypeGenerationService(db)
    try:
        run = service.start(prototype, instruction=payload.instruction)
    except GenerationInProgressError as exc:
        raise AppError(str(exc), code="generation_in_progress", status_code=status.HTTP_409_CONFLICT) from exc
    except NoPreviousVersionError as exc:
        raise AppError(str(exc), code="no_previous_version", status_code=status.HTTP_409_CONFLICT) from exc

    execution_mode = enqueue_or_run_prototype_generation(run.id, db=db)
    db.commit()
    db.refresh(run)

    return _generation_to_response(run, execution_mode=execution_mode)


@router.get("/{prototype_id}/refinements", response_model=list[RefinementHistoryItemResponse])
def list_refinements(
    prototype_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RefinementHistoryItemResponse]:
    """Histórico do "chat" de refinamento (Prompt 13, seção 2), mais
    antigo primeiro (ordem de leitura de uma conversa) — todo
    `GenerationRun` com `instruction` preenchido para este `Prototype`,
    SUCEEDED ou FAILED (a geração inicial, com `instruction=None`, nunca
    aparece aqui: ela já é a v1 na lista de versões). `joinedload` evita
    N+1 ao resolver `version_id`/`version_number` de cada entrada bem-
    sucedida."""
    get_accessible_prototype_or_404(db, prototype_id, current_user)
    runs = (
        db.query(GenerationRun)
        .options(joinedload(GenerationRun.version))
        .filter(GenerationRun.prototype_id == prototype_id, GenerationRun.instruction.isnot(None))
        .order_by(GenerationRun.created_at.asc())
        .all()
    )
    return [_refinement_to_response(r) for r in runs]


@router.get("/{prototype_id}/versions", response_model=list[PrototypeVersionListItemResponse])
def list_prototype_versions(
    prototype_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PrototypeVersionListItemResponse]:
    """Histórico de versões, mais recente primeiro (Prompt 12, seção 4) —
    inclui geração inicial, refinamentos e restaurações; NÃO inclui
    edições manuais via `PUT` (ver docstring de `PrototypeVersion`)."""
    get_accessible_prototype_or_404(db, prototype_id, current_user)
    versions = PrototypeVersionService(db).list_for_prototype(prototype_id)
    return [_version_to_list_item(v) for v in versions]


@router.get("/{prototype_id}/versions/{version_id}", response_model=PrototypeVersionDetailResponse)
def get_prototype_version(
    prototype_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrototypeVersionDetailResponse:
    get_accessible_prototype_or_404(db, prototype_id, current_user)
    version = PrototypeVersionService(db).get(prototype_id, version_id)
    if version is None:
        raise AppError(
            f"Versão {version_id} não encontrada para o protótipo {prototype_id}.",
            code="prototype_version_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _version_to_detail(version)


@router.get("/{prototype_id}/versions/{version_id}/export")
def export_prototype_version(
    prototype_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Export estático (HTML/CSS) de uma versão, como `.zip` (Prompt 15).
    Mesma autorização de qualquer outra rota de `Prototype`. Transformação
    determinística e local (sem chamada de rede, sem IA) — síncrona de
    propósito, sem fila: medido em ~2ms mesmo em `MAX_COMPONENTS_PER_PROTOTYPE`
    (300 componentes, o teto real da árvore), ordens de magnitude abaixo
    do que justificaria enfileirar. Gerado sob demanda a cada chamada,
    nunca persistido."""
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)
    version = PrototypeVersionService(db).get(prototype_id, version_id)
    if version is None:
        raise AppError(
            f"Versão {version_id} não encontrada para o protótipo {prototype_id}.",
            code="prototype_version_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        zip_bytes = build_export_zip(prototype, version)
    except (ValueError, ValidationError) as exc:
        raise AppError(
            f"Não foi possível exportar esta versão: {exc}",
            code="invalid_component_tree",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc

    filename = export_filename(prototype, version)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{prototype_id}/versions/{version_id}/restore", response_model=PrototypeVersionDetailResponse)
def restore_prototype_version(
    prototype_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrototypeVersionDetailResponse:
    """Restaura uma versão antiga criando uma versão NOVA idêntica a ela
    (Prompt 12, seção 4 — preferido a um mecanismo de rollback dedicado:
    mais simples, e consistente com o histórico sempre linear/nunca
    sobrescrito do resto do projeto). Nunca chama IA — sem custo, sem
    rate limit. Bloqueado enquanto uma geração está `PENDING` (mesmo
    motivo de `/generate`/`/refine`: evitar uma corrida entre a geração
    terminando e a restauração, que faria uma sobrescrever a outra de
    forma imprevisível)."""
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)
    version_service = PrototypeVersionService(db)
    version = version_service.get(prototype_id, version_id)
    if version is None:
        raise AppError(
            f"Versão {version_id} não encontrada para o protótipo {prototype_id}.",
            code="prototype_version_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        PrototypeGenerationService(db).validate_preconditions(prototype)
    except GenerationInProgressError as exc:
        raise AppError(str(exc), code="generation_in_progress", status_code=status.HTTP_409_CONFLICT) from exc

    restored = version_service.restore(prototype, version)
    db.commit()
    db.refresh(restored)
    return _version_to_detail(restored)
