import type {
  AuditStatus,
  ConfidenceLevel,
  DataState,
  OpportunityTier,
  SearchRunStatus,
} from "@/lib/api/types";

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatRelativeShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.round(hours / 24);
  return `há ${days} d`;
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return score.toFixed(1);
}

export const TIER_LABEL: Record<OpportunityTier, string> = {
  high: "Alta",
  medium_high: "Média-alta",
  medium: "Média",
  low: "Baixa",
  very_low: "Muito baixa",
};

export const CONFIDENCE_LABEL: Record<ConfidenceLevel, string> = {
  high: "Alta",
  medium: "Média",
  low: "Baixa",
};

export const SITE_STATE_LABEL: Record<DataState, string> = {
  confirmed: "Confirmado",
  not_detected: "Não detectado",
  inconclusive: "Inconclusivo",
  inaccessible: "Inacessível",
  not_checked: "Não verificado",
  stale: "Desatualizado",
};

export const SITE_STATE_DESCRIPTION: Record<DataState, string> = {
  confirmed: "Um site próprio foi encontrado e confirmado como acessível.",
  not_detected:
    "As fontes consultadas não indicaram um site próprio. Isso não significa necessariamente que a empresa não tenha um site — apenas que não foi encontrado.",
  inconclusive:
    "Fontes diferentes reportaram sites diferentes para esta empresa — não foi possível decidir qual (se algum) é o site oficial.",
  inaccessible:
    "Um site foi indicado, mas não foi possível acessá-lo no momento da auditoria (pode estar fora do ar temporariamente).",
  not_checked:
    "A verificação ainda não foi concluída (ex.: bloqueada por política de segurança, ou auditoria ainda não executada).",
  stale:
    "Já foi confirmado no passado, mas a confirmação expirou e precisa ser refeita.",
};

/** Explicação genérica por `DataState`, usada na seção de Evidence — nunca
 * trata ausência/inconclusão como "não existe" (Fase 0). Diferente de
 * `SITE_STATE_DESCRIPTION`, que é uma narrativa específica sobre website. */
export const EVIDENCE_STATE_HEDGE: Record<DataState, string | null> = {
  confirmed: null,
  not_detected:
    "As fontes consultadas não confirmaram este dado. Isso não significa necessariamente que ele não exista — apenas que não foi encontrado.",
  inconclusive: "A checagem foi ambígua ou incompleta — não é possível confirmar nem descartar este dado.",
  inaccessible: "Havia indício deste dado, mas não foi possível confirmá-lo no momento da checagem.",
  not_checked: "Esta checagem ainda não foi executada.",
  stale: "Já foi confirmado no passado, mas a confirmação expirou e precisa ser refeita.",
};

export const AUDIT_STATUS_LABEL: Record<AuditStatus, string> = {
  pending: "Pendente",
  running: "Em execução",
  completed: "Concluída",
  failed: "Falhou",
};

export const SEARCH_RUN_STATUS_LABEL: Record<SearchRunStatus, string> = {
  pending: "Pendente",
  running: "Em execução",
  completed: "Concluída",
  partially_completed: "Parcialmente concluída",
  failed: "Falhou",
  cancelled: "Cancelada",
};

export const EVIDENCE_FIELD_LABEL: Record<string, string> = {
  name: "Nome",
  address: "Endereço",
  phone: "Telefone",
  website: "Website",
  category: "Categoria",
  business_status: "Status do negócio",
  rating: "Avaliação (nota)",
  review_count: "Número de avaliações",
  website_accessible: "Site acessível",
  website_https: "HTTPS",
  website_status_code: "Status HTTP",
  website_title: "Título da página",
  website_meta_description: "Meta description",
  website_contact_available: "Contato disponível no site",
  website_social_links: "Links de redes sociais",
};

export function evidenceFieldLabel(field: string): string {
  return EVIDENCE_FIELD_LABEL[field] ?? field;
}

export const DIMENSION_LABEL: Record<string, string> = {
  website_gap: "Ausência de site",
  website_quality_gap: "Qualidade do site",
  digital_presence_gap: "Presença digital",
  business_visibility: "Visibilidade do negócio",
  segment_fit: "Adequação de segmento",
  contactability: "Facilidade de contato",
};

export function dimensionLabel(key: string): string {
  return DIMENSION_LABEL[key] ?? key;
}
