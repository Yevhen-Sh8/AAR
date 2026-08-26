# AAR Platform — Living Document

> **Призначення цього файлу.** Це єдиний living-документ для всіх — людей і
> AI-агентів — хто потрапляє на проєкт уперше. Тут описано: що ми будуємо,
> чому саме так (методологія), що вже зроблено, які рішення прийнято, що
> робиться зараз і що буде далі. Документ оновлюється з кожною зміною, що
> впливає на поведінку системи. Якщо ти агент — починай тут.

**Останнє оновлення:** 2026-07-22
**Поточна версія:** v1.8.0 (= v1.1 + Waves 1–10: … + Telegram notifications + geo map + dictionary CRUD)
**Активна гілка розробки:** `claude/equipment-tracking-system-3lB6U`
**Жива демо-версія:** https://yevhen-sh8.github.io/AAR/
**Робочий деплой (як підняти):** `docs/DEPLOY.md` (Docker Compose у себе / на VM)

---

## 1. Що це таке і навіщо

**AAR (After Action Review)** — це цифрова платформа для оборонного підприємства,
яка одночасно вирішує дві задачі:

1. **Пономерний облік ефективності виробів.** Кожне використання виробу
   (умовно: серія А або Б, до 10 експлуатантів Е-01..Е-10) фіксується як подія
   з результатом: успіх / втрата (5 причин а–д) / повернення в ремонт (18 причин
   а–р). Із цього автоматично виходить щоденна довідка і місячна звітність із
   рейтингом експлуатантів.

2. **Систематичне накопичення досвіду за NATO Lessons Learned Handbook 4.**
   Поверх атомарних подій система запускає тригери, відкриває AAR-кейси,
   проводить їх через цикл *Observation → Lesson Identified → Lesson Learned →
   Institutionalization* і вимірює ефективність самого циклу навчання.

Це не Excel-сховище. Це інструмент, що **замикає цикл навчання**: бачить
повторювану проблему — фіксує її — допомагає сформулювати чому — призначає
відповідального — перевіряє, що рішення подіяло (або повертає на доопрацювання,
якщо проблема повторилась).

---

## 2. Архітектура — три шари

```
┌────────────────────────────────────────────────────────────────┐
│  Шар 3: Контекст-активи (CAL v1.1)                              │
│  Patterns, facts, recommendations, narratives, classifiers      │
│  draft → validated → deprecated (ADR-007/008/009)               │
└────────────────────────────────────────────────────────────────┘
                              ▲ feeds analogies + reuse
┌────────────────────────────────────────────────────────────────┐
│  Шар 2: AAR-кейси (NATO LL cycle) — Wave 1                      │
│  open → analysed → endorsed → implemented → validated → closed  │
│  + what_was_planned / what_happened / analysis / lesson         │
│  + recommendations з auto-validation                            │
└────────────────────────────────────────────────────────────────┘
                              ▲ triggers T1..T5
┌────────────────────────────────────────────────────────────────┐
│  Шар 1: Пономерні події                                         │
│  UsageEvent {item, operator, date, outcome, reason}             │
│  Append-only · ідемпотентність по client_event_id               │
└────────────────────────────────────────────────────────────────┘
```

**Технологічний стек:**

| Шар | Технологія |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic |
| Frontend | React 18 + Vite + TypeScript, PWA (Workbox + IndexedDB) |
| База | PostgreSQL 16 (prod), SQLite in-memory (тести) |
| Черга | Redis 7 |
| LLM | Anthropic SDK — Sonnet 4.6 (default), Haiku 4.5 (fast), prompt caching |
| Інфра | Docker Compose; nginx з security headers |
| CI | GitHub Actions: ruff + mypy + pytest + pip-audit + tsc + vitest |
| Demo | GitHub Pages з зашитими mock-фікстурами (`apps/web/public/mock/*`) |

---

## 3. Методологія — чому саме така модель даних

### 3.1 Дворівнева модель

Дослідження NATO LLH4 + наукова література однозначно вказують: **спостереження
і урок — це різні сутності, і їх не можна змішувати**. Дві найпоширеніші причини
смерті LL-програм світу:

1. **«Lessons observed ≠ lessons learned».** Організація збирає спостереження,
   але ніколи не доводить їх до перевіреної зміни поведінки.
2. **Відсутність вимірюваної користі.** Не можна показати, що щось було
   попереджено — підтримка керівництва вмирає.

Наша відповідь:
- **Шар 1 (UsageEvent)** — спостереження.
- **Шар 2 (AARCase)** — Issue/LI з повним NATO state machine (Wave 1).
- **Шар 3 (ContextAsset)** — валідовані LL для повторного використання.

### 3.2 Стани AAR-кейсу — точне відображення NATO LLH4

```
OPEN → ANALYSED → ENDORSED → IMPLEMENTED → VALIDATED → CLOSED
```

| Стан | NATO етап | Чим закінчується |
|---|---|---|
| `OPEN` | Observation captured | Зібрано факт/тригер |
| `ANALYSED` | Analyse (LI identified) | Заповнено `analysis` + `lesson_identified` |
| `ENDORSED` | Endorse & Task | Призначено `opr` (відповідальний) |
| `IMPLEMENTED` | Implement | Усі рекомендації в статусі `done` |
| `VALIDATED` | Monitor & Validate | Підтверджено даними, що подіяло (auto/manual) |
| `CLOSED` | Institutionalize | Архівовано, lesson доступний у CAL |

**Жорстке правило:** не можна перестрибувати стани без явного `force=true`
(тільки адмін). Forward-only за замовчуванням. Зворотний рух (regression) —
тільки автоматичний, через двигун автовалідації, коли причина повторюється.

### 3.3 Поля AARCase і чотири класичні питання AAR

Армійська методика США (TC 25-20) ставить чотири питання. Кожне має поле:

| AAR-питання | Поле моделі |
|---|---|
| Що планувалось? | `what_was_planned` |
| Що реально сталося? | `what_happened` (+ агрегати з UsageEvent) |
| Чому це сталося? | `analysis` (обов'язкове — найчастіше пропускається) |
| Що покращити? | `lesson_identified` + `recommendations[]` |

### 3.4 Автовалідація — серце циклу

`services/recommendation_validation.py` запускається з тригер-двигуном
щодня і робить дві речі:

- **Регресія.** Якщо сигнатура (напр. `T2:loss:c`) повторно фіксується сьогодні,
  усі рекомендації зі статусом `DONE` і такою ж сигнатурою → `IN_PROGRESS`,
  ставиться `regressed_at`, інкрементується `evidence_count`. Запис в audit-лог
  (`recommendation.regressed`).
- **Підтвердження.** Якщо сигнатура не з'являлась N днів (default 14) — статус
  → `VALIDATED`, ставиться `auto_validated_at`. Запис у audit-лог
  (`recommendation.auto_validated`).

Це закриває причину смерті LL-програм №1.

### 3.5 Метрики (наукова латиниця)

Згідно `docs/metrics.md`:

| Код | Назва | Формула |
|---|---|---|
| `η` (MSR) | Mission Success Rate | success / launched |
| `η_c` (MSR_c) | Crew-adjusted MSR | success / (launched − не-обслуга втрати) |
| `λ_c` (CLR) | Crew Loss Rate | обслуга-втрати / launched |
| `ΔMSR` | Зміна MSR | η_this − η_prev |

**Каверза з MSR:** література розрізняє «вузький» (від запуску до удару) і
«повний» (зі зривами через РЕБ/погоду). У нас зараз — «вузький» від
launched-pool. Для повної інтерпретації див. `docs/metrics.md` §3.

---

## 4. Що зроблено (станом на сьогодні)

### v1.0 — на main
- Шар 1 повністю: модель, REST, CSV/XLSX імпорт, дедуплікація
- Щоденна довідка + місячний звіт + XLSX/PDF + рейтинг експлуатантів
- Тригери T1..T5 із сигнатурною ідемпотентністю
- Audit hash-chain (SHA-256, ISO 27001 A.8)
- AAR-кейс v1.0 (плаский open/in_progress/closed) + IndividualReport + Recommendation
- Інтеграційний шар (generic/ODIN/DELTA/Kropyva/SAP); **Оберіг виключено за політикою**
- Експорти за наказом № 440 (відомість, акти, журнал руху)
- Offline-first PWA + idempotent sync
- ISO/IEC 27001:2022 controls table (`docs/normative/iso-27001-controls.md`)

### v1.1 — на гілці `claude/equipment-tracking-system-3lB6U`
- **Context Accumulation Layer:** LLM-функції повертають `LLMResult[T] =
  (task_output, context_assets[])`. Активи стартують як `draft`, потребують
  людської валідації (ADR-008), пошук аналогій — тільки серед validated
  (ADR-009).
- **Повний UI:** усі placeholder-сторінки замінено реальними (Reports, Audit,
  Integrations, Context, Settings, Dictionaries).
- **GitHub Pages demo** з фіксованими mock-даними — для перегляду без бекенду.

### Wave 1 (поточний пуш) — закриття NATO циклу
- Міграція 0007 додає на `AARCase`: `what_was_planned`, `what_happened`,
  `analysis`, `lesson_identified`, `opr`, `analysis_source`, `analysis_drafted_at`.
- Розширений `CaseStatus`: open / analysed / endorsed / implemented /
  validated / closed із forward-only state machine
  (`ALLOWED_TRANSITIONS` в `models/aar.py`).
- `POST /aar/cases/{id}/transition` — рух по машині станів, з аудитом
  `case.transitioned`.
- `PATCH /aar/cases/{id}` — редагування NATO-полів; стани лише через transition.
- LLM draft-analysis тепер **зберігається в `case.analysis`** і не зникає при
  закритті кейсу; audit `case.analysis_drafted`.
- Нова таблиця колонок у `recommendations`: `evidence_count`,
  `auto_validated_at`, `regressed_at`, `signature`.
- `services/recommendation_validation.py` — двигун автовалідації + регресії,
  викликається з `evaluate_triggers`.
- Щоденна довідка тепер має блок `conclusions` (топ-3 причини, активні тригери,
  відкриті рекомендації, headline-резюме) — згідно `docs/forms/daily-template.md` §2.
- Нові аудит-дії: `case.transitioned`, `case.analysis_drafted`,
  `recommendation.auto_validated`, `recommendation.regressed`.
- Тести: `test_nato_cycle.py` (5 кейсів) — state machine, PATCH, auto-validation,
  auto-regression, daily conclusions.

### Wave 2 — Виміряти саме навчання
- Міграція 0008 додає: `usage_events.aborted` (bool) + `abort_reason` (str),
  `item_types.unit_cost_usd` (numeric), `aar_cases.validated_at` (datetime
  stamped при переході в VALIDATED).
- Нова сторінка-роутер `/learning/loop-kpi` (`routers/learning.py`) повертає
  мета-KPI циклу навчання — закриває причину смерті LL-систем #2 за
  літературою («no measurable benefit → leadership stops sponsoring»).
- `services/learning_metrics.py::compute_loop_kpi` обчислює:
  - **`time_to_validation_days_median`** і `_p90` — швидкість циклу
  - **`li_to_ll_conversion_pct`** — % кейсів, що дійшли до validated
  - **`recurrence_rate_pct`** — % валідованих рекомендацій, які регресували
  - **`open_cases_by_opr`** — навантаження на відповідальних
  - **`msr_narrow` vs `msr_full`** — обидва знаменники (з літератури:
    narrow ~43%, full 20–30%)
  - **`cost_per_effect_usd_by_type`** — cheap-mass арифметика
- Транзишн в VALIDATED тепер автоматично штампує `validated_at`.
- Нова UI-сторінка `LearningLoopPage.tsx` (маршрут `/learning-loop`,
  іконка Activity, секція «Звіти») — 4 meta-картки + MSR-double + cost-table
  + OPR-load таблиця.
- Demo mock `loop-kpi.json`.
- Тести: `test_learning_metrics.py` (7 кейсів) — endpoint shape, time_to_validation
  median, LI→LL pct, recurrence pct, MSR narrow vs full, cost-per-effect,
  OPR grouping.

### Wave 3 — Культура і поширення
- Міграція 0009: `individual_reports` отримує `anonymous` (bool),
  `requested_at`, `requested_for_user_id`; `user_id` і `submitted_at`
  стають nullable (одна модель тепер описує і запит, і подання). Таблиця
  `knowledge_entries` видалена як рудимент (ADR-014).
- Новий ендпойнт `POST /aar/cases/{id}/request-reports` — менеджер задає
  список user_ids → створюються pending-стаби, дублі пропускаються,
  webhook `individual_report.requested` шле зовнішнім системам.
- Розширений `POST /aar/cases/{id}/reports` — підтримує `request_id`
  (заповнення стаба) і `anonymous=true` (зануляє user_id у відповіді,
  audit-ланцюг зберігає originator — TC 25-20 blame-free).
- `services/notifications.py` — централізована точка для outbound
  webhook'ів. Викликається з: створення кейсу, transition, auto-validation
  рекомендації, запит звіту. Помилки доставки не блокують бізнес-операцію.
- Розширений `WebhookEventKind`: `aar_case.transitioned`,
  `recommendation.auto_validated`, `individual_report.requested`.
- UI `CasesPage`: блок «Індивідуальні звіти учасників» — лічильник
  submitted/pending, поле для розсилки запитів через user_ids, таблиця
  звітів з позначкою «анонімно» для anonymous=true.
- Тести: `test_wave3_culture.py` (6 кейсів) — створення pending stubs,
  ідемпотентність повторного запиту, заповнення стаба при подачі,
  anonymous redaction, webhook on case-created і case-transitioned,
  list pending reports. Також додано регресійний тест ADR-009
  (`test_analogies_searches_only_validated_assets`).

### Wave 4 — Робочий деплой (production)
- ~~`render.yaml`~~ — **видалено (серпень 2026).** Робочий контур розгортався
  на Render Blueprint, поки вистачало безкоштовного плану. Тепер розгортання
  своє: `infra/docker-compose.yml` локально або на VM (`docs/DEPLOY.md`).
  Vercel лишився **виключно як demo-вітрина** — статика на синтетичних даних,
  без бекенду.
- `apps/api/start.sh` — entrypoint контейнера: `alembic upgrade head` →
  ідемпотентний seed (за `AAR_SEED_ON_START`) → `uvicorn` на `$PORT`.
  Платформонезалежний — саме тому перехід із Render на власний хост не
  потребував змін у коді.
- `core/config.py` — нормалізація БД-URL: `postgres://`/`postgresql://` →
  `postgresql+asyncpg://` (+ зрізання `?sslmode=` для asyncpg). CORS тепер з
  env: `AAR_CORS_ORIGINS` (список) + `AAR_CORS_ORIGIN_REGEX` (необов'язковий
  шаблон). Прапор `AAR_SEED_ON_START`.
- `main.py` — CORS будується з налаштувань (origins + optional regex).
- `Dockerfile` (API) — копіює `start.sh`, ставить його як CMD, виставляє
  права; слухає `$PORT`.
- Фронтенд live-режим: `apps/web/src/lib/api.ts` читає `VITE_API_BASE` —
  абсолютний URL бекенду (зашивається в бандл під час білду). Default
  лишається `/api` (nginx/vite-proxy).
- CI: нова джоба `migrations` — `alembic upgrade head` на чистій БД +
  downgrade→upgrade roundtrip. Ловить клас багів, який тести (create_all)
  не бачать.
- Тести: `test_config_prod.py` (6 кейсів) — нормалізація postgres-URL,
  asyncpg-драйвер, sqlite без змін, зрізання sslmode, CORS-список.
- **Знайдено й виправлено до деплою:** міграція 0009 на SQLite падала
  (`batch_alter_table` + зміна nullability → recreate таблиці з безіменними
  FK). Виправлено `naming_convention` у batch (на Postgres — no-op).

### Wave 5 — Автентифікація і прод-загартування
- `POST /auth/login` (`routers/auth.py`) — обмін email+пароль на JWT;
  email case-insensitive; однакова помилка на «немає юзера» і «невірний
  пароль» (не зливаємо існування акаунтів).
- `GET /auth/me` — поточний користувач для UI.
- Глобальний auth-gate як HTTP middleware у `main.py`: у `production`
  будь-який шлях, окрім невеликого allow-list (`/`, `/auth/login`, `/health/*`,
  `/docs`, `/redoc`, `/openapi.json`), вимагає валідний Bearer-токен.
  У `development` вимкнено, щоб тести/розробка лишались frictionless
  (узгоджено з dev-bypass у `core/rbac.require_role`).
- `core/security.py`: схема паролів змінена з `bcrypt` на `pbkdf2_sha256` —
  чистий Python, без passlib↔bcrypt 4.x несумісностей (інакше падало і в
  тестах, і в проді).
- Сід-скрипт створює bootstrap-адміна з `AAR_ADMIN_EMAIL` /
  `AAR_ADMIN_PASSWORD`.
- Фронтенд: `lib/auth.ts` (localStorage-сесія + подія `aar:unauthorized`);
  `LoginPage` (екран входу); `App.tsx` рендерить логін, якщо не авторизований
  і не demo-режим; сайдбар має «Вийти». `api.ts` і `sync.ts` ставлять
  `Authorization: Bearer <token>` і на 401 чистять сесію та шлють на логін.
- `render.yaml`: `AAR_ADMIN_EMAIL`/`AAR_ADMIN_PASSWORD` (sync:false для пароля).
- Тести: `test_auth.py` (7) — login успіх/неуспіх/case-insensitive, `/me` з/без
  токена, allow-list публічних шляхів, гейт блокує без токена в проді й
  пропускає з токеном.

**Знайдений і виправлений баг (той самий реліз):** `_seed_admin` спершу
робив create-once — якщо admin-рядок вже існував, скрипт мовчки пропускав
seed, тож зміна `AAR_ADMIN_PASSWORD` у Render **не мала жодного ефекту**
після першого успішного старту контейнера (пароль замерзав на значенні
з першого boot). Це і викликало «невірний email або пароль» при першій
спробі логіну в проді. Виправлено на upsert: `_seed_admin` тепер
синхронізує хеш пароля існуючого admin-рядка з поточним
`AAR_ADMIN_PASSWORD` при **кожному** старті — редагування змінної в Render
+ авто-редеплой тепер справді працює як «скинути пароль». Регресійний тест
`test_seed_admin.py::test_seed_admin_syncs_password_on_rerun` фіксує
цю поведінку. Підказку з дефолтним паролем на екрані входу після
підтвердження, що логін працює, **видалено** (див. нижче) — публічний
екран не повинен розкривати креденшели анонімному відвідувачу.

### Wave 5 (продовження) — Загартування без блокування + швидкість

- **CORS звужено.** `AAR_CORS_ORIGINS` у `render.yaml` тепер явний список
  (`aar-web.onrender.com` + GitHub Pages demo) замість `*`. Логіка в
  `main.py` і раніше підтримувала обидва режими (wildcard/explicit) —
  змінилось лише значення в конфігу.
- **Security response headers** (`main.py::security_headers` — HTTP
  middleware, застосовується до кожної відповіді, включно з 401 від
  auth-гейту): `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`,
  `Content-Security-Policy` (м'якша політика на `/docs`/`/redoc`, бо
  Swagger UI тягне бандл із `cdn.jsdelivr.net`).
- **Rate limiting на `/auth/login`** — `core/rate_limit.py::SlidingWindowLimiter`,
  in-process (без Redis — його немає в `render.yaml`), ключ за
  `X-Forwarded-For`/client IP, дефолт 20 спроб / 5 хв
  (`AAR_LOGIN_RATE_LIMIT_ATTEMPTS`/`_WINDOW_SECONDS`). Понад ліміт → `429` +
  `Retry-After`. Скидається автоскид-фікстурою в `conftest.py` між тестами.
- **Non-blocking warning на дефолтний пароль:** якщо в production
  `AAR_ADMIN_PASSWORD` досі дорівнює хардкодженому дефолту — лог-попередження
  при старті (не hard-fail, на відміну від відсутнього `AAR_JWT_SECRET`,
  який і далі падає — там ціна помилки вища).
- **Прибрано публічну підказку логіна.** `LoginPage` більше не показує
  дефолтний email/пароль — це працювало як діагностика на етапі, коли
  логін не спрацьовував (баг вище), але лишати його на проді означає
  розкривати креденшели будь-кому, хто відкриє URL.
- **Browser-only бекап.** `GET /admin/export` (роль ADMIN, у dev — bypass)
  віддає повний JSON-знімок робочих таблиць (без хешів паролів) як
  файл-завантаження. `SettingsPage` → картка «Резервна копія» з кнопкою.
  Компенсує те, що free-план Postgres на Render не робить автобекапів і
  живе 90 днів, а керування деплоєм — лише з браузера (без термінала).
  Це супровідна страховка, не заміна point-in-time recovery.
- **Code-splitting фронту.** `App.tsx` — усі сторінки, крім `LoginPage`,
  через `React.lazy` + `<Suspense>`; `vite.config.ts` — `manualChunks` для
  vendor-бандлів (react, react-router, react-query, recharts, lucide-react).
  Головний entry-чанк впав із ~658 KB до ~13.6 KB (gzip ~5.4 KB); важкі
  залежності (recharts ~365 KB) вантажаться лише при заході на відповідну
  сторінку і кешуються окремо від коду сторінок.
- Тести: `test_rate_limit.py` (2), `test_security_headers.py` (2),
  `test_admin_export.py` (2) — 86/86 backend тестів зелені разом з рештою.

### Wave 6 — Проактивні сигнали (до виконання завдання)

Реалізація концепції «Проактивна взаємодія» з двох документів користувача
(канонічно зафіксовані у `docs/concept/positioning.md`; там же — таблиця
відповідності «особливості з концепції ↔ що вже реалізовано»).

- **Ідея:** система працює не лише ПІСЛЯ завдання (класичний AAR), а й на
  етапі ПІДГОТОВКИ — будь-який користувач заздалегідь реєструє попередження,
  ризик, пропозицію чи інформаційний сигнал; відповідальна особа розглядає;
  цикл навчання замикається (висновки AAR → підготовка → нові сигнали →
  база досвіду).
- Міграція 0010: таблиця `pre_task_signals` (kind: warning/risk/proposal/
  info; статуси new → acknowledged → accepted/dismissed/converted;
  nullable `author` — анонімне подання за тією ж blame-free логікою, що
  ADR-015; `case_id` — зв'язок із кейсом при ескалації).
- Роутер `/signals`: подання, список із фільтрами, `POST /{id}/review`
  (acknowledge/accept/dismiss + нотатка; термінальні статуси фінальні),
  `POST /{id}/convert` — створює AAR-кейс, передзаповнений із сигналу
  (`what_happened` = текст спостереження), лінкує назад.
- Аудит-дії `signal.created/reviewed/converted`; webhook `signal.created`
  (доставка партнерам не блокує подання).
- UI: сторінка «Сигнали (до завдання)» (перша в секції AAR) — форма подання
  (тип, контекст завдання, анонімність), журнал зі статусними чіпами й
  кнопками розгляду/конвертації; demo-mock `signals.json`.
- Тести: `test_signals.py` (3) — create+list+фільтри, review-життєвий цикл
  із guard'ами термінальних станів, конвертація в кейс (+ audit-запис).

### Wave 7 — Брифінг підготовки місії (AAR як вхід у планування)

Реалізує пункт 3 стратегії постачання (positioning.md §5): продукт для
планувальника, а не для аналітика.

- `services/mission_brief.py` — агрегація за профілем завдання (ключові
  слова + тип виробу + експлуатант) у єдиний пакет: активні сигнали
  (Wave 6), валідовані уроки з CAL (**тільки** validated — ADR-009,
  draft ховається навіть при збігу), уроки з кейсів у статусі
  validated/closed, відкриті рекомендації, об'єктивна статистика подій
  (MSR, топ-причини втрат, зриви окремо, вікно 90 днів).
- Релевантність — детермінований підрахунок токен-збігів (без LLM:
  брифінг має бути миттєвим і працювати офлайн). З запитом — фільтр
  zero-hit + сортування за релевантністю; без запиту — найновіші відкриті.
- `GET /briefing/mission` (за auth-гейтом у production, як усі не-public
  шляхи).
- `BriefingPage` («Брифінг місії», перший пункт секції AAR): форма профілю,
  картка статистики, 4 секції з кольоровим кодуванням, кнопка друку.
  Demo-mock `briefing.json`.
- **LLM-синтез поверх брифінгу** (`GET /briefing/mission/synthesis`):
  `services/llm.py::synthesize_mission_brief` перетворює агрегований пакет
  у планувальницький тезовий брифінг — `headline`, `key_risks`
  (risk/evidence/mitigation, кожен зі згадкою даних пакету),
  `precautions`, `confidence_note`. Той самий патерн, що й решта LLM
  (LLMResult[T], structured output, cache_control ephemeral на system-блоці);
  draft-активи, які помітив, персистяться (ADR-008, дія користувача). Gated:
  503 при вимкненому LLM. GET-triggers-LLM — як `/llm/cases/{id}/analogies`.
  UI: кнопка «Синтез ШІ» на `BriefingPage` (фіолетова картка з ризиками й
  застереженнями), demo-mock `briefing-synthesis.json`. **Спирається
  ВИКЛЮЧНО на дані пакету** (промпт забороняє вигадувати факти).
- Тести: `test_mission_brief.py` (6) — фільтрація статистики за
  типом/вікном зі зривами окремо; ранжування за запитом (dismissed-сигнали
  й draft-активи не показуються); режим без запиту; втрати під час зривів
  у top_loss_reasons; синтез 503 при вимкненому LLM; синтез happy-path
  (mocked) з перевіркою compact-payload.
- Виправлено під час розробки: двоентітний `select(...)` через
  `.scalars()` мовчки губить другу сутність — замінено на `.execute()`.

**Рев'ю-цикл (оркестрація 4 вимірів + адверсарна верифікація).** Після
базової реалізації запущено багатоагентний review-workflow (correctness /
security / consistency / ux, кожна знахідка → окремий агент-скептик).
З 6 кандидатів після аналізу проти коду виправлено 5:
- **F1 (medium, correctness):** втрата під час зриву (ADR-012 дозволяє
  aborted+lost) не потрапляла в `top_loss_reasons` — EW-важкий профіль
  брифувався як lost=0. Тепер усі втрати живлять risk-сигнал; додано
  `lost_during_abort` (окремо від `lost`, щоб інваріант
  launched=success+lost+repaired зберігся). Тест-guard додано.
- **F2 (medium):** тип виробу у фільтрі був хардкодом A/B → у проді з
  реальними кодами фільтр мертвий. Тепер `BriefingPage` тягне
  `/dictionaries/item-types` (як інші сторінки).
- **F3 (low):** вікно було `window_days+1` (off-by-one проти triggers.py)
  і без верхньої межі. Тепер `today - (N-1)` + `event_date <= today`
  (майбутньо-датовані події не роздувають статистику).
- **F5 (low):** unicode-гліфи в заголовках секцій → замінено на
  lucide-іконки (конвенція решти UI).
- **F6 (low):** demo показував порожню сторінку до кліку → у demo-режимі
  авто-запит на монтуванні (як сусідні demo-сторінки).
- **F4 (medium) — частково:** «необмежене завантаження таблиць» — додано
  безпечний `_CANDIDATE_CAP=500` на кандидатні запити сутностей; віконне
  сканування подій для статистики лишено (узгоджено з
  `learning_metrics.py` + ADR-013 — це sanctioned aggregation pattern, не
  list-endpoint).

### Хвиля 8 — Telegram-канал сповіщень + гайд пілоту

- **Telegram-конектор** поверх наявного webhook-шару (`services/integrations.py`):
  новий `ConnectorKind.TELEGRAM`. Підписка: `target_url` = chat_id,
  `secret` = токен бота. Диспетчер для telegram будує людське повідомлення
  (`_telegram_text`, HTML parse_mode, escape динамічних полів) і постить на
  `https://api.telegram.org/bot<token>/sendMessage`; **токен лишається в
  secret і ніколи не потрапляє ні в тіло, ні в підпис-заголовок**. Мінімальна
  зміна `_post` (гілка на kind) — сигнатура збережена, наявні тести цілі.
- UI `IntegrationsPage`: для типу telegram поля перепідписуються (Chat ID /
  Токен бота) + підказка про @BotFather. Demo-mock конектора оновлено.
- Тест: `test_telegram_dispatch_hits_bot_api_with_message` — правильний
  URL Bot API, chat_id у тілі, людський текст, токен не в заголовках.
- **`docs/PILOT.md`** — чек-лист запуску пілоту (Трек A): увімкнення AI,
  налаштування довідників, фіксація базової лінії, операційний цикл
  день/тиждень, підключення Telegram, підсумок «до/після» як цифра для
  постачання.

### Хвиля 9 — Геокарта подій

- `GET /events/geojson` (`routers/events.py`) — геоприв'язані події як
  GeoJSON FeatureCollection із фільтрами (дати, outcome, operator_code,
  item_type_code, limit≤5000). Тільки події з `location` (Point);
  properties несуть коди (serial/operator/item type) для тултипів + outcome
  для кольору. Тести: `test_events_geojson.py` (2) — лише геоприв'язані,
  коди в properties, фільтр за outcome.
- `MapPage` («Геокарта», секція Аналітика) — **self-contained SVG-плот без
  зовнішніх тайл-серверів** (ADR-022): свідомо без базової картографічної
  підложки, щоб не залежати від OSM і не розкривати районів інтересу
  (узгоджено з offline-first + політикою секретності, як виключення Оберіг).
  Лінійна проєкція lon/lat на viewBox за bbox даних, graticule з підписами,
  точки за кольором outcome (успіх/втрата/ремонт), фільтри, tooltip і
  панель деталей по кліку. Demo-mock `events-geojson.json`.

### Хвиля 10 — CRUD довідників через UI

- `routers/dictionaries.py` розширено з read-only до повного CRUD для всіх
  чотирьох довідників (типи виробів, експлуатанти, причини втрат/ремонтів):
  `POST` / `PATCH` / `DELETE`, запис лише для ролі `admin` (`require_role`).
- `code` унікальний і **незмінний після створення** (дублікат → 409);
  редагуються назва, зона, вартість.
- **Захист посилальної цілісності:** `DELETE` → 409, якщо на код посилаються
  події/предмети/кейси — класифікатор не можна прибрати з-під наявного обліку.
- Кожен запис іде в audit hash-chain (`DICTIONARY_CREATED/UPDATED/DELETED`).
- Фронтенд `DictionariesPage` — інлайн додавання/редагування/видалення в таблиці;
  у demo лише читання. Побіжно виправлено баг відображення назв (`name` → `name_uk`).
- Тести: `test_dictionaries.py` (3).

### Хвилі 11–12 — учасники, зворотний зв'язок автору, атрибуція свідчень

- **Довідник людей** (`PeoplePage`, `routers/people.py`): ПІБ, позивний,
  експлуатант за замовчуванням, функція в події. Особа без пароля — нормальний
  запис: її можна зробити учасником кейсу, але в систему вона не входить.
  Приналежність до експлуатанта **впорядковує підказки і ніколи не обмежує
  вибір** — свідчення ззовні (виробник, РЕБ) не дає списати все на екіпаж.
- **Поверхня учасника** (`MyReportsPage`, `GET /aar/my-report-requests`,
  `GET /aar/my-observations`): «від мене чекають» + форма шести питань AAR і —
  головне — «що вийшло з моїх спостережень». Автор бачить не «звіт прийнято»,
  а фразу-наслідок («Зміна впроваджена і підтверджена даними»). Обидва
  ендпойнти навмисно на `optional_claims`, а не `require_role`: останній у
  `development` коротшає до ADMIN, а персональні дані мають падати закрито.
- **Смужка покриття** й UI рекомендацій у `CasesPage`; `POST /llm/...` відмовляє
  синтезувати аналіз кейсу без жодного поданого свідчення (409).

**Дірка в атрибуції свідчень (знайдено й закрито при перевірці Хвилі 12).**
`POST /aar/cases/{id}/reports` мав захист від підміни, але той спрацьовував
лише коли викликач сам передавав `user_id` — а UI учасника його не передає
ніколи. Тобто будь-який автентифікований учасник міг надіслати
`{request_id: <запит колеги>}` і отримати **201**: свідчення лягало в чужий
запит, а незмінний ланцюг аудиту записував автором колегу. Те саме без
запиту — `POST {user_id: <колега>}`.

- Перевірка тепер на **викликачеві**, а не на полі запиту
  (`_speaking_for_another`): свій запит — можна; чужий — 403.
- Запис зі слів лишається дозволеним для `admin` / `manager` / `analyst` (в
  осіб із довідника навмисно немає облікових записів), але це **привілейована
  дія**, і ланцюг фіксує два різні факти: `originator_user_id` — чиє свідчення,
  `transcribed_by` — хто набрав.
- `transcribed_by` редагується для анонімних звітів нарівні з originator: хто
  саме набрав — звужує коло авторів у малому підрозділі.
- `user_id` тепер проставляється на неанонімному звіті (раніше лишався `NULL`,
  і кожне подання виглядало анонімним на рівні рядка).
- Тести: `test_report_attribution.py` (7), `test_my_observations.py` (7),
  `test_participants.py` (7).

---

## 5. Що НЕ зроблено і чому

| Робота | Стан | Чому відкладено |
|---|---|---|
| Реальний Signal-канал нотифікацій | планується | Telegram-канал реалізовано (Хвиля 8); Signal — за потреби |
| Шифрування at-rest / point-in-time backup / ротація секретів | планується (Wave 6) | Потребує платного плану Postgres + інфраструктурних рішень замовника; JSON-експорт (Wave 5) — лише проміжна страховка |
| Live integrations з DELTA/Kropyva (реальні ключі) | поза MVP | Потребує продуктивних ключів і нормативного дозволу |
| Матеріалізовані view для KPI (prod scale) | Wave 6 | На поточному масштабі агрегати < 100 мс (ADR-013) |
| Розподілений (Redis) rate-limit | Wave 6 | Потрібен лише якщо деплой масштабується на кілька інстансів |

---

## 6. Рішення (ADR-журнал, скорочено)

> **Примітка (серпень 2026).** ADR-017…020 ухвалювались у контексті деплою на
> Render. Від Render відмовились (безкоштовний план перестав покривати
> потреби), `render.yaml` видалено. Самі рішення лишаються чинними — вони про
> нормалізацію БД-URL, розділення фронтенду й бекенду, in-process rate-limit і
> JSON-бекап, а не про конкретного провайдера. Текст ADR не переписуємо:
> журнал рішень — історичний запис, а не опис поточного стану.

> **Це канонічний журнал архітектурних рішень проєкту (ADR-001…022).**
> `docs/PROJECT.md` §6 посилається сюди й не веде власної нумерації.

- **ADR-001** — Стек Python+FastAPI + React+Vite + Postgres. *Чому:* типобезпека,
  async-first, екосистема ML/LLM.
- **ADR-002** — Метрики в латиниці (η, η_c, λ_c). *Чому:* виноска до наукової
  літератури по дронах.
- **ADR-003** — Оберіг виключено з інтеграцій. *Чому:* таємна система, не
  ставиться в публічному компоненті.
- **ADR-004** — ISO/IEC 27001:2022 замість КСЗІ. *Чому:* запит замовника; ISO
  закриває майже всі КСЗІ-вимоги без проходження ДСТСЗІ-сертифікації для MVP.
- **ADR-005 (концепт)** — Дворівнева модель: атомарні події (Рівень 1) →
  якісні AAR-кейси (Рівень 2). *Чому:* розділяє кількісний і якісний шар, як
  радить NATO LL; append-only події + hash-chain (ADR аудиту) дають цілісність
  обліку за наказом № 440.
- **ADR-006 (концепт)** — PWA замість нативного мобільного, offline-first
  (Workbox + IndexedDB + черга синхронізації). *Чому:* один кодбейс, робота
  без звʼязку в полі, простіше розгортання.
- **ADR-007** — Дворезультатний LLM-патерн: `LLMResult[T] = (task, assets)`.
- **ADR-008** — Активи завжди стартують як `draft`. Ніколи auto-validate.
- **ADR-009** — `find_analogies` шукає тільки серед `validated`.
- **ADR-010 (новий, Wave 1)** — NATO state machine жорстка, forward-only.
  Регресія дозволена лише автоматичній автовалідації, не людині-вручну.
- **ADR-011 (Wave 1)** — LLM draft зберігається в кейс. Поле `analysis`
  оновлюється тільки якщо було порожнім (не перетирає людський текст).
- **ADR-012 (Wave 2)** — `aborted` як окрема булева, не виокремлений Outcome.
  *Чому:* зриви — це аспект події (не дійшло до запуску), результат лишається
  валідним (Outcome відображає підсумок саме того, що могло статися). Дає
  ортогональні розрізи: можна aborted+success (зрив перед тим, як виріб встиг
  зробити свою справу — рідкий, але можливий) і aborted+lost (виріб втрачено
  під час підготовки).
- **ADR-013 (Wave 2)** — мета-KPI рахуються «на льоту» (без матеріалізованих
  view). *Чому:* при наявному масштабі (десятки тисяч подій, сотні кейсів)
  агрегати робляться за <100 мс; матеріалізація додасть інваріантів і
  буде окремою задачею Wave 4 (production scale).
- **ADR-014 (Wave 3)** — модель `KnowledgeEntry` видалена. *Чому:* v1.1 CAL
  (`ContextAsset`) повністю її заміщує; жоден router у v1.1 не пише в стару
  таблицю. Залишати мертвий код = плутати агентів і додавати maintenance cost.
- **ADR-015 (Wave 3)** — анонімність зберігається в API-відповіді (user_id=null),
  але audit-ланцюг тримає originator. *Чому:* TC 25-20 культура вимагає,
  щоб учасник довіряв системі; одночасно адмін має право розслідувати
  зловживання (фейкові звіти). Двошарова видимість.
- **ADR-016 (Wave 3)** — pending-request і submitted-report — це одна модель
  з двома станами (`submitted_at` null/не-null), а не дві окремі сутності.
  *Чому:* життєвий цикл «запросили → людина подала» — це той самий
  семантичний об'єкт; розділення на дві моделі породжує синхронізацію
  без виграшу в моделюванні.
- **ADR-017 (Wave 4)** — один `AAR_DATABASE_URL` для всіх середовищ;
  нормалізація драйвера в `config.py`, а не різні env для async/sync.
  *Чому:* керовані хостинги (Render/Heroku/Railway) дають `postgres://` без
  драйвера; зводимо до `postgresql+asyncpg://` в одному місці, Alembic зрізає
  `+asyncpg` для sync. Менше конфіг-дрейфу між dev/prod.
- **ADR-018 (Wave 4)** — фронтенд на проді — окремий статичний сайт із
  абсолютним `VITE_API_BASE`, а не реверс-проксі перед бекендом. *Чому:* CDN
  безкоштовний і не засинає; API `root_path="/api"` приймає префікс, тож
  абсолютний `…/api/...` працює; CORS-regex для `*.onrender.com` знімає
  крихкість іменування сервісів.
- **ADR-019 (Wave 5)** — rate-limit на логін тримається в пам'яті процесу,
  без Redis. *Чому:* Redis не піднятий у `render.yaml` для цього пілоту;
  in-process sliding window достатньо для одного інстансу і захисту від
  базового перебору паролів. Явно задокументовано як обмеження — не
  захищає розподілену атаку і скидається при рестарті.
- **ADR-020 (Wave 5)** — бекап як admin-only JSON-ендпойнт, а не
  CLI/pg_dump-скрипт. *Чому:* деплой керується виключно з браузера (без
  термінала); JSON-експорт можна викликати кнопкою й одразу отримати файл.
  Це свідомо не претендує на роль point-in-time recovery — задокументовано
  як «супровідна страховка», справжній бекап/restore — платний план
  Postgres на Render.
- **ADR-021 (Wave 6)** — проактивні сигнали — окрема легка сутність
  (`PreTaskSignal`), а не «кейс у статусі draft». *Чому:* поріг подання має
  бути мінімальним (заголовок + тип, можна анонімно), інакше учасники не
  подаватимуть; повний NATO-цикл кейсу для «попередження про погоду» —
  надмірний. Ескалація в кейс — явна дія відповідальної особи (convert),
  а не автоматична.
- **ADR-022 (Wave 9)** — геокарта подій — самодостатній SVG-плот
  (`MapPage.tsx`), а не тайлова карта (Leaflet/Mapbox/OSM). *Чому:* тайлові
  движки тягнуть плитки з зовнішнього сервера тайлів на кожен рух карти —
  це і залежність від стороннього хоста (offline-first ламається), і витік
  районів інтересу оператора в чужі логи. Проекція lon/lat робиться
  локально по bbox активних подій; сервер віддає лише `GET /events/geojson`.
  Узгоджено з політикою секретності (як виключення «Оберіг», ADR-003) та
  offline-first.

---

## 7. Roadmap наступних хвиль

**Хвиля 2 — Виміряти саме навчання — ✅ ЗАВЕРШЕНА (поточний реліз)**
- ✅ Дашборд мета-KPI: time-to-validation, % LI→LL, recurrence rate, OPR-навантаження
- ✅ Розрізнення MSR-narrow / MSR-full (поле `aborted` на UsageEvent)
- ✅ Cost-per-effect
- ✅ UI для transitions (кнопки в CasesPage) — зроблено у Wave 1
- ⚠ LL-flywheel віджети на головному dashboard — flywheel винесено в окрему
  сторінку `/learning-loop`. На головному `/` поки немає — буде у Wave 2.5
  якщо буде попит (зараз окрема сторінка дає більше місця і це чіткіше).

**Хвиля 3 — Культура і поширення — ✅ ЗАВЕРШЕНА (поточний реліз)**
- ✅ Неатрибутивний режим (anonymous flag з audit-збереженням originator)
- ✅ Розсилка форм учасникам (request-reports workflow з ідемпотентністю)
- ✅ Webhook'и на події кейсів і auto-validation
- ⚠ Bulk-imports інтерфейс окремого UI для звітів немає — для подій
  існує `/import`. Якщо буде потреба — додамо у Wave 5.
- ✅ Видалено рудимент `KnowledgeEntry`

**Хвиля 4 — Робочий деплой — ✅ ЗАВЕРШЕНА (поточний реліз)**
- ✅ Бекенд на Render/Fly з Postgres — `render.yaml` Blueprint + `docs/DEPLOY.md`
- ✅ Self-migrate + idempotent seed на старті контейнера (`start.sh`)
- ✅ Env-driven CORS + нормалізація БД-URL + live-режим фронтенду
- ✅ CI-джоба міграцій (fresh-DB upgrade + roundtrip)
- ⚠ TLS/secrets-vault/JWT-rotation/backup-drill — Render дає TLS і
  generated-secret «з коробки»; повний прод-контур безпеки = Wave 5
- ☐ Pilot у однієї військової частини — потребує рішення замовника

**Хвиля 5 — Автентифікація і загартування без блокування — ✅ ЗАВЕРШЕНА (поточний реліз)**
- ✅ Повна автентифікація: JWT-логін, глобальний auth-гейт, вихід, upsert
  admin-пароля
- ✅ CORS звужено з `*` до явного списку доменів
- ✅ Security response headers (CSP, X-Frame-Options, HSTS, тощо)
- ✅ Rate-limit на `/auth/login` (in-process, 20/5хв)
- ✅ Browser-only JSON-бекап (`/admin/export` + кнопка в Налаштуваннях)
- ✅ Code-splitting фронту (658 KB → ~13.6 KB головний чанк)
- ☐ Pilot у однієї військової частини — потребує рішення замовника

**Хвиля 6 — Повне прод-загартування (за потреби)**
- Шифрування at-rest, справжній point-in-time backup + restore-drill,
  JWT-rotation, приватна мережа/VPN
- Реальний Signal-канал поверх webhook-шару (Telegram уже реалізовано, Хвиля 8)
- Матеріалізовані view для KPI (якщо масштаб зросте); Redis-based rate-limit
  (якщо деплой стане багатоінстансовим)

---

## 8. Як читати код (для агентів)

| Хочу зрозуміти… | Йду в |
|---|---|
| Як влаштована подія | `apps/api/aar_api/models/event.py` |
| Як працює тригер | `apps/api/aar_api/services/triggers.py` |
| Як рахується щоденна довідка | `apps/api/aar_api/services/reports.py` |
| Як працює state-machine кейсу | `apps/api/aar_api/models/aar.py` (`ALLOWED_TRANSITIONS`) |
| Як LLM зберігає чернетку | `apps/api/aar_api/routers/llm.py` (`draft_case_analysis`) |
| Як автовалідація | `apps/api/aar_api/services/recommendation_validation.py` |
| Як влаштовано audit-chain | `apps/api/aar_api/services/audit.py` |
| Як виглядає UI-сторінка | `apps/web/src/pages/<ім'я>.tsx` |
| Як працює demo-режим | `apps/web/src/lib/api.ts` (DEMO + MOCK_ROUTES) |
| Як працює live-режим (прод) | `apps/web/src/lib/api.ts` (`VITE_API_BASE`) |
| Як підняти робочий додаток | `docs/DEPLOY.md` + `render.yaml` + `apps/api/start.sh` |
| Як bootstrapнути локально | `CLAUDE.md` § Build & Test Commands |
| Формальна документація (паспорт/опис/настанова) | `docs/passport/` (ЄСПД/ДСТУ) |

---

## 9. Як вносити зміни (для агентів)

1. **Прочитай цей файл повністю.** Тут є відповіді на більшість «чому так?».
2. Перевір, чи твоя задача збігається з якоюсь хвилею в §7. Якщо ні —
   обговори з користувачем, перш ніж кодити.
3. Будь-яка зміна моделі даних → Alembic-міграція + оновлення тестів +
   оновлення цього файлу (§4 і §6).
4. Будь-яка зміна, що зачіпає LL-цикл → додай ADR-запис у §6.
5. Зміна стану `CaseStatus` → перевір `ALLOWED_TRANSITIONS`.
6. Нові LLM-функції → завжди в патерні `LLMResult[T]` (ADR-007/008).
7. Зміна форматів звітів → онови `docs/forms/*`.
8. Перед пушем: `ruff check . && mypy aar_api && pytest -q` (API) +
   `tsc -b && npm run build && npm test` (web).
9. **Завжди оновлюй цей файл** після значущої зміни. Це не сторонній doc, це
   контракт із наступним агентом.

---

## 10. Корисні посилання

- NATO LL Handbook 4th ed. (JALLC, 2022): https://www.jallc.nato.int/articles/4th-edition-nato-lessons-learned-handbook-available-now
- JALLC Analysis Handbook 2024
- US Army TC 25-20 «A Leader's Guide to After-Action Reviews»
- Brave1 / DELTA — українська екосистема feedback-loop:
  https://en.wikipedia.org/wiki/Brave1
- Repo: https://github.com/yevhen-sh8/aar
- PR з Wave 1: https://github.com/yevhen-sh8/aar/pull/4
- Demo: https://yevhen-sh8.github.io/AAR/

---

*Цей файл — жива пам'ять проєкту. Якщо ти змінюєш код — зміни і його.*
