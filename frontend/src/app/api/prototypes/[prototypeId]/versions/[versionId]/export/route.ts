import "server-only";
import { getSessionToken } from "@/lib/auth/session";

/**
 * Proxy de download do export estático (Prompt 15).
 *
 * `lib/api/client.ts` (o cliente HTTP normal do resto do frontend) sempre
 * espera/devolve JSON — não serve para um `.zip` binário. Precisa ser um
 * Route Handler, não uma Server Action: o botão de export é literalmente
 * um link (`<a href>`), e só um Route Handler pode responder a uma
 * navegação do navegador com um arquivo para download
 * (`Content-Disposition: attachment`).
 *
 * O browser nunca fala direto com o backend FastAPI (mesma arquitetura
 * Browser → Next.js → FastAPI do resto do app, `lib/api/client.ts`) — o
 * token de sessão nunca é exposto ao navegador; este handler o anexa no
 * servidor e repassa a resposta binária como está. Sem token, o fetch ao
 * backend simplesmente omite o header `Authorization`, e o backend (a
 * autoridade real de autenticação, `get_current_user`) responde 401 —
 * nunca duplicamos essa checagem aqui.
 */
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ prototypeId: string; versionId: string }> }
) {
  const { prototypeId, versionId } = await params;
  const token = await getSessionToken();

  let backendResponse: Response;
  try {
    backendResponse = await fetch(
      `${API_BASE_URL}/api/prototypes/${prototypeId}/versions/${versionId}/export`,
      {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        cache: "no-store",
      }
    );
  } catch (cause) {
    console.error(`[export] falha de rede ao exportar ${prototypeId}/${versionId}:`, cause);
    return new Response("Não foi possível conectar à API do Prospect AI.", { status: 502 });
  }

  if (!backendResponse.ok || backendResponse.body === null) {
    return new Response(null, { status: backendResponse.status });
  }

  return new Response(backendResponse.body, {
    status: 200,
    headers: {
      "Content-Type": backendResponse.headers.get("content-type") ?? "application/zip",
      "Content-Disposition": backendResponse.headers.get("content-disposition") ?? "attachment",
    },
  });
}
