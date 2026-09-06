# Prospect AI — Dashboard (Fase 5)

Interface Next.js (App Router) sobre a API do backend (`../backend/`,
Fases 0-4). Ver **`../docs/dashboard.md`** para a arquitetura completa
(Server Components/Server Actions, shadcn/ui, segurança, testes,
limitações conhecidas).

## Rodando localmente

Requer o backend já no ar (padrão: `http://localhost:8000`).

```bash
cp .env.example .env.local   # ajuste API_BASE_URL se necessário
npm install
npm run dev
```

Abre em `http://localhost:3000`.

```bash
npm run build && npm run start   # build de produção
npm run lint                     # ESLint
npm run test                     # Vitest
```

## Estrutura

```
src/
  app/           # rotas (App Router): dashboard, prospects, pesquisas, configuracoes
  components/    # ui/ (shadcn), badges/, layout/, dashboard/, prospects/,
                 # prospect-detail/, discovery/, shared/
  lib/           # api/ (cliente HTTP server-only + tipos), format.ts, utils.ts
```

Nenhuma API key (Google Maps, Anthropic) passa por este projeto — elas
ficam exclusivamente em `backend/.env`; o frontend só conversa com o
backend Python, nunca diretamente com um provider externo.
