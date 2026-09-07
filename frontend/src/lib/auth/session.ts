import "server-only";
/**
 * Sessão do usuário no Next.js (Fase 7).
 *
 * O token JWT emitido pelo backend (`POST /api/auth/login`) é guardado em
 * um cookie httpOnly — nunca em `localStorage`/`sessionStorage`, que seria
 * legível por qualquer script no navegador. O browser nunca vê o token em
 * texto plano fora do cookie; toda chamada à API do Prospect AI continua
 * passando pelo servidor Next.js (`lib/api/client.ts`), que anexa o
 * `Authorization: Bearer <token>` — a arquitetura Browser → Next.js →
 * FastAPI (Prompt 11, seção 2.4) não muda.
 */
import { cookies } from "next/headers";

export const SESSION_COOKIE_NAME = "pai_session";

const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24; // 24h — mesmo prazo do JWT (JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

export async function getSessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE_NAME)?.value ?? null;
}

export async function setSessionToken(token: string): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: COOKIE_MAX_AGE_SECONDS,
  });
}

export async function clearSessionToken(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE_NAME);
}
