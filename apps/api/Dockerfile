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
RUN pip install --no-cache-dir -e .

USER app
EXPOSE 8000
CMD ["uvicorn", "aar_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
