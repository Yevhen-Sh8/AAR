#!/usr/bin/env sh
# Production entrypoint (Wave 4).
#
# Runs DB migrations, optionally seeds idempotent demo data, then launches the
# ASGI server bound to the platform-provided $PORT (Render/Fly/Railway set this;
# defaults to 8000 for local Docker).
set -e

echo "[start] applying database migrations…"
alembic upgrade head

if [ "${AAR_SEED_ON_START}" = "true" ] || [ "${AAR_SEED_ON_START}" = "1" ]; then
  echo "[start] seeding demo data (idempotent)…"
  python -m aar_api.scripts.seed || echo "[start] seed skipped/failed (non-fatal)"
fi

PORT="${PORT:-8000}"
echo "[start] launching uvicorn on 0.0.0.0:${PORT}"
exec uvicorn aar_api.main:app --host 0.0.0.0 --port "${PORT}"
