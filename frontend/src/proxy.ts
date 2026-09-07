import { NextResponse, type NextRequest } from "next/server";

// Duplicado deliberadamente de `lib/auth/session.ts` (não importado daqui):
// aquele módulo carrega `next/headers`, cuja API não é a usada pelo runtime
// de Edge Middleware (que lê cookies via `NextRequest.cookies`) — manter os
// dois desacoplados evita depender de compatibilidade de bundling entre
// contextos de execução diferentes por causa de uma única string.
const SESSION_COOKIE_NAME = "pai_session";

/**
 * Primeira linha de defesa (Fase 7): redireciona para `/login` quando não
 * há cookie de sessão. Isto é só uma checagem de PRESENÇA do cookie, nunca
 * uma validação de assinatura/expiração — a autorização de verdade é
 * sempre feita pelo backend (`get_current_user`, FastAPI) a cada chamada de
 * API; se o token estiver expirado/inválido, a chamada volta 401 e a
 * página trata isso como erro (nunca finge sucesso). Rodar em `proxy`
 * (convenção do Next.js 16 — renomeada de `middleware`, ver AGENTS.md)
 * evita que a UI protegida sequer comece a renderizar sem sessão.
 */
const PUBLIC_PATHS = ["/login", "/register"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api).*)"],
};
