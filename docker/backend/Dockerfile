FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docker/backend ./docker/backend
COPY scripts/check_migration_safety.py ./scripts/check_migration_safety.py
COPY README.md ./README.md

RUN sed -i 's/\r$//' /app/docker/backend/*.sh && \
    chmod +x /app/docker/backend/start-api.sh /app/docker/backend/start-worker.sh /app/docker/backend/start-prewarm.sh

EXPOSE 8000

CMD ["/bin/sh", "/app/docker/backend/start-api.sh"]
