# CHANGELOG

Усі суттєві зміни концепції, архітектури та документації проєкту.
Формат: [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/),
семантика дат — `РРРР-ММ-ДД`.

## [v0.2.0-data-model] — 2026-05-11

### Added (Етап 2 — модель даних і довідники)
- Моделі: `ItemType`, `Operator`, `LossReason`, `RepairReason` із зоною
  відповідальності (`operator/manufacturer/external/unknown`), `Item`
  (пономерний), `UsageEvent` (з `outcome ∈ {success, lost, repair}`),
  `AARCase`, `IndividualReport`, `Recommendation`, `KnowledgeEntry`.
- Alembic-міграція `0002_data_model`.
- Pydantic-схеми + REST: `GET /dictionaries/*`, `POST /events`,
  `GET /events?date_from&date_to&operator_code&outcome`.
- Валідація події: `outcome=lost` ⇒ обовʼязковий `loss_reason_code`,
  `outcome=repair` ⇒ `repair_reason_code`, `success` не може нести причину.
- Seed-скрипт `python -m aar_api.scripts.seed` створює довідники
  (А/Б, Е-01…Е-10, a–e, a–r) і ~3000 синтетичних подій листопад–грудень
  з фіксованим seed=42.
- Тести `tests/test_events.py` (in-memory SQLite через aiosqlite).

### Fixed
- `ruff` config: додано `flake8-bugbear.extend-immutable-calls` для
  `fastapi.Depends/Query/Path/Body/Header`; `extend-per-file-ignores` для
  alembic-міграцій.

## [v0.1.0-skeleton] — 2026-05-11

### Added (Етап 1 — скелет монорепо)
- `apps/api`: FastAPI + SQLAlchemy 2 + Alembic; ендпоінт `/health`;
  JWT-утиліти (`core/security.py`), модель `User` з ролями
  (`participant/analyst/manager/admin/integrator`).
- `apps/web`: React 18 + Vite + TypeScript + PWA (Workbox); сторінки
  Дашборд / Події / AAR-кейси; роутинг через react-router.
- `infra/docker-compose.yml`: Postgres 16, Redis 7, api, web.
- `packages/shared/classifiers.json`: початкові класифікатори
  (А/Б, a–e, a–r) з посиланням на зону відповідальності.
- CI (`.github/workflows/ci.yml`): ruff, mypy, pytest для API;
  build + vitest для web.
- `.env.example`, `.gitignore`, Dockerfile для обох застосунків.
- Початкова міграція Alembic `0001_initial` (таблиця `users`).

### Changed
- `docs/PROJECT.md`: статус оновлено до Етап 1.

### Fixed (по результатах архітектурного ревʼю Plan-агента)
- CI: прибрано npm cache (немає lockfile), додано окремий tsc-крок.
- API: FastAPI змонтовано на `root_path="/api"`; `/health/live` + `/health/ready`
  з пінгом БД; CORS — лише локальні origin замість `*`; fail-fast на JWT
  secret поза dev.
- Dockerfile API: правильний порядок COPY перед `pip install -e .`,
  додано `setuptools.packages.find` і non-root user; `.dockerignore`
  для api та web.
- nginx: узгоджено префікс `/api/`, додано security headers (CSP, XFO,
  Referrer-Policy, X-Content-Type-Options).
- mypy: пом'якшено зі `strict=true` до `warn_unused_ignores/redundant_casts`,
  щоб CI не валився на python-jose / passlib без стабів.
- Прибрано `schemas/auth.py` — auth-роутер з'явиться на Етапі 2.
- Модель `User.role` тепер `sa.Enum(Role, native_enum=False)` замість сирого
  `String`.

## [v2.0-concept] — 2026-05-11

### Added
- Концепція AAR v2.0 з модулем «Облік і ефективність виробів»
  (`docs/concept/AAR_v2.md`).
- Шаблони щоденної довідки та місячної звітності (`docs/forms/`).
- Перелік сценаріїв автоматизації A1–A12 (`docs/automation.md`).
- Дорожня карта Етапів 0–10 (`docs/roadmap.md`).
- Нормативна база: огляд, наказ № 440, NATO LL, gap-аналіз (`docs/normative/`).
- Живий довідник проєкту (`docs/PROJECT.md`).
- Цей `CHANGELOG.md`.
- Оновлений `README.md` як точка входу.

### Decided (ADR)
- Стек: Python + FastAPI / React PWA / PostgreSQL / Redis / Docker Compose
  on-prem.
- Інтеграції MVP: лише CSV/Excel імпорт від виробництва.
- Безпека: ISO/IEC 27001:2022 + ISO/IEC 27002:2022 (не КСЗІ).
- Нормативка: працюємо з публічними редакціями наказів № 440 / № 90 / № 687.

### Pending
- Реальні класифікатори а–д та а–р від замовника (поки абстрактні).
- Інтеграції DELTA / «Кропива» / SAP / «Оберіг» — Етап 9.
