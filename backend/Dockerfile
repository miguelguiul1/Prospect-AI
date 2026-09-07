FROM python:3.12-slim

# Usa 3.12 (uma tag estável e amplamente disponível) em vez da 3.14 usada
# no desenvolvimento local, para não depender de uma imagem oficial recém-
# publicada. Nenhuma dependência do requirements.txt exige uma versão
# específica de Python acima de 3.10 — mas esta imagem AINDA não foi
# construída nem executada em nenhuma sessão deste projeto (Fases 0-8),
# porque nenhuma máquina usada até aqui tem Docker disponível. Ver
# docs/production-readiness.md.

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# `/health` não toca banco/Redis (ver app/api/routes/health.py) — seguro
# como liveness probe: nunca reporta "unhealthy" só porque uma dependência
# externa está lenta. Usa Python (já presente na imagem) em vez de
# curl/wget, que a imagem `-slim` não inclui por padrão.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" || exit 1

# Aplica as migrations e sobe a API a cada início de container.
#
# NOTA (achado da auditoria F8.0, seção 15/18): rodar migration no boot de
# TODA réplica é simples e correto para o estágio atual do projeto (deploy
# de uma única instância, sem rolling deploy real ainda validado) — mas em
# um rolling deploy com múltiplas réplicas, isso significa que a primeira
# réplica nova a subir aplica a migration enquanto réplicas antigas ainda
# atendem tráfego com o código anterior. Nenhuma migration até a Fase 8 é
# breaking (todas são aditivas), então isso nunca foi um problema real —
# mas se uma migration breaking futura precisar de zero-downtime de
# verdade, migrar para um job de deploy separado (fora do boot do
# container) é a mudança recomendada nesse momento, não antes.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
