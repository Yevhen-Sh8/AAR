# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

AAR (After Action Review) — a defense operational intelligence platform for per-serial-number equipment tracking, effectiveness analytics, and structured knowledge accumulation. Two-level data model: atomic usage events (Level 1) feed into qualitative AAR cases (Level 2). Methodology follows NATO Lessons Learned Handbook 4.

## Monorepo Layout

- `apps/api/` — Python 3.12 backend (FastAPI + SQLAlchemy 2 async + Alembic)
- `apps/web/` — React 18 + Vite + TypeScript PWA (offline-first via Workbox + IndexedDB)
- `infra/` — Docker Compose (Postgres 16, Redis 7, api, web)
- `packages/shared/` — shared classifiers JSON (placeholder codes a–e / a–r)
- `docs/` — living documentation: `PROJECT.md` (entry point), concept, normative, forms, metrics, roadmap

## Build & Test Commands

### Backend (from `apps/api/`)

```bash
pip install -e ".[dev]"          # install with dev deps
ruff check .                      # lint
mypy aar_api                      # type check
pytest -q                         # run all tests (37 tests, in-memory SQLite)
pytest tests/test_events.py -q    # run single test file
pytest -k "test_trigger_t1" -q    # run single test by name
```

### Frontend (from `apps/web/`)

```bash
npm install
tsc -b                            # type check
npm run build                     # production build
npm test                          # vitest (3 tests)
```

### Docker (from `infra/`)

```bash
docker compose up                 # starts db + redis + api + web
# API at localhost:8000/api, Web at localhost:8080
```

### CLI scripts (from `apps/api/`, require real Postgres)

```bash
python -m aar_api.scripts.seed                        # generate synthetic Nov-Dec data
python -m aar_api.scripts.daily_report --date 2025-11-15 --out ./out
python -m aar_api.scripts.monthly_report --year 2025 --month 12 --out ./out
python -m aar_api.scripts.run_triggers --date 2025-12-15
```

## Architecture

### Backend layers (apps/api/aar_api/)

```
core/           config (pydantic-settings, AAR_ prefix), db (async engine), security (JWT), rbac
models/         SQLAlchemy ORM: user, dictionaries, event, aar, audit, context, integration
schemas/        Pydantic request/response models per domain
routers/        FastAPI routers — each domain has its own file
services/       Business logic: reports, monthly, triggers, llm, audit, context_assets,
                exports (XLSX/PDF), mod440 (Order #440 forms), integrations (webhook dispatch)
scripts/        CLI entrypoints for cron (daily_report, monthly_report, run_triggers, seed)
```

FastAPI mounts at `root_path="/api"`. Nginx (in web container) proxies `/api/` to the api container.

### Key patterns

- **Tests use in-memory SQLite** via `conftest.py` setting `AAR_DATABASE_URL=sqlite+aiosqlite:///:memory:`. Every test gets fresh tables (autouse fixture creates/drops all). No Postgres needed for tests.
- **Settings** read from env with `AAR_` prefix (`AAR_DATABASE_URL`, `AAR_JWT_SECRET`, etc.). `get_settings()` is `@lru_cache` — call `get_settings.cache_clear()` in tests when patching env.
- **Async throughout** — all DB operations use `AsyncSession`, all routers are `async def`.
- **Alembic migrations** in `apps/api/alembic/versions/` (6 migrations, 0001–0006). Migration `env.py` strips `+asyncpg` for sync Alembic driver.

### Two-result LLM pattern (v1.1)

Every LLM function returns `LLMResult[T] = (task_output, context_assets[])`. The router persists draft assets via `services/context_assets.persist_drafts()`. Context assets start as `draft` and require human validation — never auto-validated (ADR-008). `find_analogies` queries only `validated` assets (ADR-009).

LLM prompts use `output_config.format` with JSON-schema (structured outputs) and `cache_control={"type": "ephemeral"}` on stable system-prompt blocks.

### Audit hash-chain

`services/audit.py` implements append-only SHA-256 chain (genesis = 64 zeros). Each entry hashes `(action, actor, entity_type, entity_id, payload, prev_hash)`. `verify_chain()` walks all rows and returns the first broken ID. Critical actions (event create, case open/close, context asset transitions) write audit entries.

### Trigger engine

`services/triggers.evaluate_triggers(session, today)` checks rules T1–T4 over a sliding window. Cases are idempotent via a `[T#:key:date]` signature in the title — duplicate runs skip.

### Integration layer

Outbound webhooks with per-target shape adapters (generic/ODIN/DELTA/Kropyva/SAP). HMAC-SHA256 signing in `X-AAR-Signature`. GeoJSON Point on `UsageEvent.location`. Inbound events idempotent on `(source, external_id)`.

### Offline PWA

`apps/web/src/lib/db.ts` (IndexedDB via `idb`) + `sync.ts` (queue + flush). Events carry `client_event_id` (UUID); server deduplicates on unique index. `installAutoSync()` listens to `online` event.

## Metrics notation

Scientific Latin names — see `docs/metrics.md`:
- `MSR` (η) = Mission Success Rate = success / sorties
- `MSR_c` (η_c) = Crew-adjusted MSR (excludes external/manufacturer losses)
- `CLR` (λ_c) = Crew Loss Rate
- Code fields: `msr`, `msr_c`, `clr`, `delta_msr_pp`, `msr_prev`, `msr_this`

## Environment variables

All prefixed `AAR_`. Key ones: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ENVIRONMENT` (development|production), `ANTHROPIC_API_KEY`, `LLM_ENABLED` (bool), `LLM_DEFAULT_MODEL`, `LLM_FAST_MODEL`.

## Conventions

- Ruff line length 100, rules E/F/I/B/UP. Alembic migrations exempt from UP/I rules.
- `fastapi.Depends/Query/Path/Body/Header` are in `extend-immutable-calls` (no B008 false positives).
- Owner enums (`Role`, `Zone`, `Outcome`, `AssetStatus`, etc.) stored as `native_enum=False` strings in DB.
- Ukrainian for user-facing labels in XLSX/PDF exports; English for code identifiers and API field names.
- Documentation updates required for any behavior change — see `docs/PROJECT.md` §7.
