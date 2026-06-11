FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 app

COPY pyproject.toml ./
COPY aar_api ./aar_api
COPY alembic ./alembic
COPY alembic.ini ./
COPY start.sh ./
RUN pip install --no-cache-dir -e . \
 && chmod +x start.sh \
 && chown -R app:app /app

USER app
EXPOSE 8000
# Entrypoint runs migrations (+ optional seed) then starts uvicorn on $PORT.
CMD ["./start.sh"]
