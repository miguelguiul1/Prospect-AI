import "server-only";
import { apiGet, apiPost } from "@/lib/api/client";
import type { TokenResponse, UserResponse } from "@/lib/api/types";

export function login(email: string, password: string): Promise<TokenResponse> {
  return apiPost<TokenResponse>("/api/auth/login", { email, password });
}

export function register(email: string, name: string, password: string): Promise<TokenResponse> {
  return apiPost<TokenResponse>("/api/auth/register", { email, name, password });
}

export function getCurrentUser(): Promise<UserResponse> {
  return apiGet<UserResponse>("/api/auth/me");
}

/** Nunca lança — usada em locais (ex.: layout raiz) que precisam saber "há
 * um usuário logado?" sem tratar "não" como uma condição de erro. */
export async function getCurrentUserSafe(): Promise<UserResponse | null> {
  try {
    return await getCurrentUser();
  } catch {
    return null;
  }
}
