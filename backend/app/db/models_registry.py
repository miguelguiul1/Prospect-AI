"""Importa todos os modelos para registrá-los em `Base.metadata`.

O Alembic (`migrations/env.py`) importa este módulo antes de comparar o
schema — sem isso, autogenerate só enxergaria os modelos que já tivessem
sido importados por acaso em outro lugar do processo.
"""
from app.domains.audit.models import AuditSnapshot, WebsiteQuality  # noqa: F401
from app.domains.auth.models import User  # noqa: F401
from app.domains.briefing.models import SalesBrief  # noqa: F401
from app.domains.companies.models import Category, Company, Region  # noqa: F401
from app.domains.crm.models import Activity, Contact, Opportunity, PipelineStage  # noqa: F401
from app.domains.discovery.models import ProviderUsageRecord, SearchRun  # noqa: F401
from app.domains.evidence.models import Evidence  # noqa: F401
from app.domains.identity.models import (  # noqa: F401
    CompanySource,
    DedupCandidate,
    IdentityMergeLog,
)
from app.domains.outreach.models import Outreach  # noqa: F401
from app.domains.prototypes.models import Prototype  # noqa: F401
from app.domains.scoring.models import OpportunityScore  # noqa: F401
