FROM python:3.12-slim

# Usa 3.12 (uma tag estável e amplamente disponível) em vez da 3.14 usada
# no desenvolvimento local desta fase, para não depender de uma imagem
# oficial recém-publicada. Nenhuma dependência do requirements.txt exige
# uma versão específica de Python acima de 3.10 — mas esta imagem NÃO foi
# construída nem executada nesta implementação (não há Docker disponível
# no ambiente em que a Fase 0 foi implementada); validar o build antes de
# depender dela. Ver README.md, seção "Limitações conhecidas desta Fase 0".

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Aplica as migrations e sobe a API. Ainda sem workers de Discovery/Audit —
# eles chegam nas fases futuras com seu próprio processo/serviço.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
