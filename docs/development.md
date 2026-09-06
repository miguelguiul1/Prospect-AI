# Guia de desenvolvimento — Fase 2

## Ambiente em que as Fases 0-2 foram implementadas (e por que isso importa)

A máquina usada tem **Python 3.14** e **Node**, mas **não tem Docker, WSL,
PostgreSQL nem Redis instalados**. Isso foi verificado diretamente (não
presumido) antes de começar a Fase 0, e o usuário optou explicitamente por
não instalar nada disso. As Fases 1 e 2 herdam a mesma limitação —
consequências práticas, documentadas para quem continuar este projeto:

1. **Os testes automatizados rodam contra SQLite**, não PostgreSQL. O
   Alembic aplica a migration real (`alembic upgrade head`) contra um
   arquivo SQLite temporário — isso valida que a migration executa e que o
   schema resultante sustenta os modelos, mas **não** valida
   comportamento específico do PostgreSQL (ex.: `ENUM` nativo — que nem é
   usado, ver `data-model.md`), locking, `JSONB`, extensões como
   `pg_trgm` que fases futuras vão precisar).
2. **`docker compose up` não foi executado nem validado nesta máquina.**
   O `docker-compose.yml` e o `backend/Dockerfile` foram escritos e
   revisados manualmente, mas ninguém os rodou de fato. Antes de confiar
   neles, rode `docker compose up --build` em uma máquina com Docker e
   confirme que os três serviços sobem e `/health` responde.
3. **`enqueue_or_run_discovery()` nunca exercitou o caminho enfileirado de
   verdade.** Sem Redis, toda chamada a `POST /api/discovery/search` nesta
   máquina passa pelo fallback síncrono (ver `docs/discovery.md`). O
   caminho `queue.enqueue(...)` está implementado e coberto por testes que
   validam que o *fallback* funciona quando a fila falha, mas ninguém
   confirmou ainda, com um Redis e um worker do RQ reais, que um job
   enfileirado é de fato processado por um worker separado.

Se você tem Docker disponível, a validação completa (Postgres real, Redis
real, `docker compose up`, um worker do RQ real) é o próximo passo
recomendado antes de iniciar a Fase 2.

## Pré-requisitos

- Python 3.12 ou superior (testado com 3.14).
- Docker + Docker Compose, para rodar com PostgreSQL/Redis reais
  (opcional para desenvolvimento pontual do schema, mas necessário para
  qualquer fase que de fato converse com um banco Postgres ou uma fila
  Redis real).

## Configuração

```bash
cd backend
cp .env.example .env
# edite .env se necessário — nenhum valor de exemplo é um segredo real
```

## Rodando com Docker (recomendado quando disponível)

```bash
docker compose up --build
```

Sobe PostgreSQL, Redis e o backend (que aplica as migrations
automaticamente antes de iniciar o Uvicorn). A API fica em
`http://localhost:8000`.

## Rodando o backend sem Docker

Requer PostgreSQL e Redis acessíveis nos endereços configurados em `.env`.

```bash
cd backend
python -m venv .venv
# Windows (Git Bash): source .venv/Scripts/activate
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# Linux/Mac: source .venv/bin/activate
pip install -r requirements-dev.txt

alembic upgrade head
uvicorn app.main:app --reload
```

## Rodando os testes

```bash
cd backend
pip install -r requirements-dev.txt  # se ainda não instalado
pytest -v
```

Os testes **não** exigem PostgreSQL/Redis reais — `tests/conftest.py`
aponta `DATABASE_URL` para um arquivo SQLite temporário e aplica as
migrations reais nele antes da suíte rodar. O teste
`test_health_dependencies_reports_redis_failure_without_masking_it` inclusive
depende de não haver um Redis real disponível na porta usada — ele existe
para provar que o endpoint de diagnóstico reporta a falha de dependência
honestamente, em vez de mascará-la. Nenhum teste do domínio `discovery`
(`tests/discovery/`) chama a API do Google de verdade — todos usam
`httpx.MockTransport` ou um provider falso, exceto o teste marcado
`@pytest.mark.external`, que é ignorado por padrão (ver `docs/discovery.md`).

Se `tests/discovery/` parecer lento na sua máquina, é o mesmo motivo do
item 3 acima: cada tentativa de usar o cache best-effort do Discovery
(`app/domains/discovery/cache.py`) tenta conectar ao Redis configurado nos
testes (`redis://localhost:6399/0`, uma porta sem serviço). O cliente
Redis usa um timeout de socket curto (`app/jobs/queue.py`) exatamente para
que isso falhe rápido em vez de travar — se notar lentidão de qualquer
forma, é o primeiro lugar a investigar.

## Rodando uma busca de Discovery localmente

Com o backend no ar (`uvicorn app.main:app --reload`) e uma
`GOOGLE_MAPS_API_KEY` real configurada em `backend/.env`:

```bash
curl -X POST http://localhost:8000/api/discovery/search \
  -H "Content-Type: application/json" \
  -d '{"region": "Interlagos", "city": "São Paulo", "category": "restaurantes", "max_results": 5}'
```

A resposta traz o `id` do `SearchRun`. Sem Redis disponível (como nesta
máquina), a busca já roda de forma síncrona antes de a resposta voltar; com
Redis, consulte o resultado depois em:

```bash
curl http://localhost:8000/api/discovery/runs/<id>
```

Sem `GOOGLE_MAPS_API_KEY` configurada, a chamada continua respondendo
`202` — o `SearchRun` volta com `status: "failed"` e uma mensagem de erro,
nunca um 500. Ver `docs/discovery.md` para o fluxo completo, os limites
internos e o teste opcional contra a API real.

## Inspecionando uma decisão de Identity Resolution

`POST /api/identity/resolve` é só leitura — não precisa de uma busca de
Discovery rodando, nem de API key nenhuma:

```bash
curl -X POST http://localhost:8000/api/identity/resolve \
  -H "Content-Type: application/json" \
  -d '{"source": "openstreetmap", "external_id": "node/1", "name": "REST. SAO JOAO", "phone": "+5511987654321"}'
```

Devolve a decisão (`match`/`no_match`/`inconclusive`), a confiança, as
razões e, se houver, o `matched_company_id` — sem persistir nada. Ver
`docs/identity-resolution.md` para os sinais usados e os limiares
configuráveis.

## Criando uma nova migration

Sempre que um modelo em `app/domains/*/models.py` mudar:

```bash
cd backend
alembic revision --autogenerate -m "descrição da mudança"
```

Revise o arquivo gerado em `migrations/versions/` antes de aplicar — o
autogenerate do Alembic é um ponto de partida, não a palavra final,
especialmente para mudanças em `Enum` ou em constraints.

## Estrutura de diretórios

```
backend/
  app/
    core/                  # config, logging, erros, middleware
    api/routes/            # health, discovery, identity
    db/                    # base declarativa, sessão, registro de modelos
    domains/
      discovery/           # DiscoveryQuery, DTO, normalização, service, jobs, cache
        providers/         # contrato + GooglePlacesProvider
      identity/            # matching, profile, service (Fase 2)
      companies/, evidence/, audit/, scoring/, briefing/
    jobs/                  # abstrações de job e conexão com a fila
  migrations/              # Alembic (3 migrations)
  tests/
    discovery/             # testes do domínio discovery (sem chamadas reais)
    identity/              # testes do domínio identity (sem chamadas reais)
frontend/        # ainda não iniciado (ver frontend/README.md)
infra/           # notas de infraestrutura (o docker-compose.yml fica na raiz)
docs/            # este diretório
```

## Por que não há `poetry`/`pipenv`

A máquina de desenvolvimento não tinha nenhum gerenciador de pacotes
Python além do `pip` padrão. Um `requirements.txt` com versões travadas
(`==`) cobre a necessidade real desta fase (instalação reprodutível) sem
introduzir uma ferramenta adicional. Revisitar essa escolha faz sentido se
o projeto crescer a ponto de precisar de grupos de dependências mais
complexos do que "produção" e "desenvolvimento".
