FROM python:3.12-slim AS base

WORKDIR /app

# System deps needed to build psycopg2 from source if no wheel matches
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY entrypoint.sh .
COPY scripts/ ./scripts/
RUN chmod +x entrypoint.sh

# Non-root user — never run a production container as root
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Runs migrations then starts the app — see entrypoint.sh for why this
# replaced a direct uvicorn CMD (create_all() was removed from app
# startup after it caused a multi-worker race condition).
CMD ["./entrypoint.sh"]
