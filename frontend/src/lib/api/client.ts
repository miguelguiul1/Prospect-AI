/**
 * Cliente HTTP mínimo para a API do Prospect AI (backend/, Fases 0-7).
 *
 * Roda SOMENTE no servidor Next.js (Server Components e Server Actions) —
 * nunca em um Client Component. Isso é o que garante que `API_BASE_URL`
 * (e qualquer detalhe de rede do backend, incluindo o token de sessão)
 * nunca aparece na aba de rede do navegador: o browser só conversa com o
 * próprio Next.js.
 *
 * Desde a Fase 7, todo request anexa automaticamente
 * `Authorization: Bearer <token>` a partir do cookie httpOnly de sessão
 * (`lib/auth/session.ts`) — este é o ÚNICO lugar do frontend que lê o
 * cookie e monta esse header (Prompt 11, seção 2.4: "centralize"). Rotas
 * públicas do backend (`/api/auth/login`, `/api/auth/register`,
 * `/api/health`) simplesmente ignoram um header ausente ou irrelevante.
 *
 * Todo erro vira um `ApiError` com uma mensagem já segura para exibir ao
 * usuário (nunca um stack trace) — o detalhe técnico completo é sempre
 * registrado via `console.error` antes de lançar, para os logs do
 * servidor Next.js.
 */
import "server-only";
import { getSessionToken } from "@/lib/auth/session";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface BackendErrorBody {
  error?: { code?: string; message?: string };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getSessionToken();
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  } catch (cause) {
    console.error(`[api] falha de rede ao chamar ${path}:`, cause);
    throw new ApiError(
      "Não foi possível conectar à API do Prospect AI. Verifique se o backend está no ar.",
      0,
      "network_error"
    );
  }

  if (!response.ok) {
    let body: BackendErrorBody = {};
    try {
      body = (await response.json()) as BackendErrorBody;
    } catch {
      // corpo não era JSON — segue com a mensagem genérica abaixo.
    }
    const code = body.error?.code ?? "unknown_error";
    const detail = body.error?.message ?? response.statusText;
    console.error(`[api] ${path} respondeu ${response.status} (${code}): ${detail}`);
    throw new ApiError(friendlyMessage(response.status, detail), response.status, code);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function friendlyMessage(status: number, detail: string): string {
  if (status === 401) return "Sua sessão expirou. Faça login novamente.";
  if (status === 403) return "Você não tem permissão para esta ação.";
  if (status === 404) return "Não encontrado.";
  if (status === 409) return detail || "A operação não pode ser concluída no estado atual.";
  if (status === 422) return "Dados inválidos.";
  if (status === 429) return detail || "Muitas tentativas. Aguarde um momento e tente novamente.";
  if (status >= 500) return "O servidor encontrou um erro inesperado.";
  return detail || "Ocorreu um erro inesperado.";
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiDelete<T = void>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}
