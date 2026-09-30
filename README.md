# Prospect AI

Uma ferramenta interna que encontra pequenos negócios da região com presença digital fraca, avalia o que falta no site deles e me ajuda a preparar uma proposta com protótipo.

> Projeto em desenvolvimento. Não tem versão pública no ar: roda localmente.

## O problema

Boa parte do meu trabalho é fazer site para comércio de bairro. Achar quem precisa de um site, olhar o que a empresa já tem online e montar uma proposta levava horas por empresa, tudo manual. O Prospect AI automatiza a parte repetitiva para eu gastar tempo no que importa: conversar com o dono e fazer um bom site.

## Como funciona

1. **Descoberta:** busca empresas por categoria e região na Google Places API.
2. **Identidade:** junta registros duplicados da mesma empresa.
3. **Auditoria digital:** visita o site público (quando existe) e mede sinais como HTTPS, responsividade, SEO básico e contato visível.
4. **Opportunity Score:** uma nota determinística, sem IA, que indica onde um site novo faria mais diferença.
5. **Sales Brief:** a IA (Claude) resume a análise num briefing de conversa.
6. **Protótipo:** um editor gera e refina uma primeira versão da página, por componentes ou por linguagem natural.
7. **CRM:** pipeline, contatos e histórico de cada oportunidade.

O sistema só trabalha com dados comerciais públicos (nome da empresa, site, telefone comercial publicado). Nenhuma base de contatos real está no repositório: os testes usam dados fictícios.

## Tecnologias

- **Backend:** Python, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL, Redis + RQ, httpx, structlog
- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, Vitest
- **IA:** Claude API para o briefing e a geração de protótipos
- **Infra:** Docker Compose, CI com testes do backend e do frontend

## Rodando localmente

Com Docker:

```bash
git clone https://github.com/miguelguiul1/Prospect-AI.git
cd Prospect-AI
cp backend/.env.example backend/.env   # a chave do Google Maps é opcional para subir
docker compose up --build
```

A API sobe em `http://localhost:8000`. Para o painel:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev   # http://localhost:3000
```

Sem Docker (com PostgreSQL e Redis próprios), os testes e os detalhes de cada módulo estão em [`docs/development.md`](docs/development.md). A visão técnica completa, com endpoints e limitações conhecidas, fica em [`docs/visao-tecnica.md`](docs/visao-tecnica.md).

## Licença

[MIT](LICENSE)
