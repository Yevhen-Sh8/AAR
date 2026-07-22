# CHANGELOG

Усі суттєві зміни концепції, архітектури та документації проєкту.
Формат: [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/),
семантика дат — `РРРР-ММ-ДД`.

## [1.8.0 — CRUD довідників через UI] — 2026-07-22

### Added
- **Повний CRUD довідників** (типи виробів, експлуатанти, причини втрат/ремонтів):
  - Бекенд `routers/dictionaries.py`: `POST` / `PATCH` / `DELETE` для кожного
    довідника. Запис — лише для ролі `admin` (`require_role`); читання відкрите.
  - `code` унікальний і **незмінний після створення** (редагуються назва, зона,
    вартість); дублікат коду → `409`.
  - **Захист від видалення використовуваного коду**: `DELETE` повертає `409`,
    якщо на запис посилаються події/предмети/кейси (не осиротюємо облік).
  - Кожен запис пише подію в audit hash-chain (`DICTIONARY_CREATED/UPDATED/DELETED`).
  - `ItemTypeOut` тепер віддає `unit_cost_usd`.
  - Тести `test_dictionaries.py` (3): roundtrip, in-use guard, зона+audit.
- Фронтенд `DictionariesPage`: додавання/редагування/видалення прямо в таблиці
  (інлайн-редагування, підтвердження видалення, показ помилок 409). У demo —
  тільки читання.

### Fixed
- `DictionariesPage` показував назви як «—»: читав поле `name`, тоді як API
  віддає `name_uk`. Виправлено.

## [Track A — шаблон «до/після»] — 2026-07-22

### Added
- `docs/BEFORE_AFTER_TEMPLATE.md` — самостійний заповнюваний артефакт для особи,
  що ухвалює постачання: паспорт заміру (однакова тривалість періодів, обсяг
  вибірки), таблиця показників (η/MSR, η_c/MSR_c, λ_c/CLR, recurrence, час до
  валідації, LI→LL, cost-per-effect) з нотацією за `metrics.md`, блок
  застережень про порівнянність і висновок/рекомендацію з підписом OPR.
  Мета — «цифра для постачання» на власних даних підрозділу.

### Changed
- `docs/PILOT.md` §6 і `docs/PROJECT.md` §2 — посилання на шаблон заміру.

## [Track A — рольові швидкі старти] — 2026-07-21

### Added
- `docs/QUICKSTART_ROLES.md` — одна сторінка на роль (експлуатант, аналітик,
  планувальник місії, менеджер AAR/OPR, адміністратор/інтегратор): мета, які
  екрани, кроки щодня/щотижня, що НЕ входить у роль. Назви пунктів меню звірені
  з навігацією застосунку. Найчастіша причина провалу пілоту — люди не знають,
  куди тиснути; цей документ це закриває.

### Changed
- `docs/PILOT.md` §4 і `docs/PROJECT.md` §2 — посилання на рольові швидкі старти.

## [Track A — пілотна документація] — 2026-07-21

### Added
- `docs/AI_ENABLEMENT.md` — гайд з увімкнення й відповідального використання
  ШІ: що роблять ШІ-функції, модель довіри (два результати, чернетки ніколи
  не авто-валідуються — ADR-008), і **точний перелік даних, що виходять у
  зовнішній LLM-API** (агреговані коди + вільний текст уроків/сигналів;
  без серійних номерів і координат). Для секретних контурів — тримати
  `AAR_LLM_ENABLED=false`.

### Changed
- `docs/PILOT.md` §1 — попередження прочитати `AI_ENABLEMENT.md` перед
  увімкненням ключа.
- `docs/PROJECT.md` §2 — карта документації доповнена рядками DEPLOY / PILOT /
  AI_ENABLEMENT.

## [v1.1.0-context-accumulation] — 2026-05-13

### Added (Етап 11 — Context Accumulation Layer)
- Реалізація моделі **«Agent → Task Output + Reusable Context Asset»**
  згідно з [design doc](docs/concept/v1.1-context-accumulation.md).
- Нові сутності: `ContextAsset` (8 типів) + `AssetUsage` (audit reuse).
- Міграція `0006_context_assets`.
- LLM-функції тепер повертають `LLMResult[T] = (task_output, context_assets[])`
  з PEP 695 generic; промпти просять JSON-масив активів за схемою.
- Validation lifecycle через сервіс `services/context_assets.py`:
  `persist_drafts` / `validate_asset` / `reject_asset` / `deprecate_asset`
  / `validated_assets` / `record_usage`. Кожна транзиція пише
  специфічну `AuditAction.CONTEXT_ASSET_*` у hash-chain audit.
- REST `/context/*`: list+filter (`type`, `status`, `source_agent`),
  get, create (manual draft), validate (M/A/Admin), reject (M/A/Admin),
  deprecate (M/Admin).
- `find_analogies` тепер шукає **лише серед validated assets** (ADR-009),
  записує `AssetUsage` для кожного матча (інкрементує `usage_count`).
- LLM-роутер автоматично персистить чернетки активів після кожного
  виклику через `_persist_assets_if_any` helper.

### Tests
- `tests/test_context.py` (5 нових): manual create starts as draft;
  full lifecycle (draft→validate→deprecate); reject 409 на не-draft;
  classify persists drafts; list filters by type/status.
- Усього 37/37 pytest ✓.

### Quality (after `simplify` review of three agents)
- 4 справжніх баги виправлено:
  1. `AuditAction` — додано 4 специфічних значення для context_assets,
     прибрано зловживання `CASE_CREATED`/`RECOMMENDATION_UPDATED`.
  2. `owner_role` — типізовано як `Role` enum (замість `String(32)`).
  3. `find_analogies` — мігровано з legacy `KnowledgeEntry` на
     `validated_assets()` (ADR-009).
  4. `record_usage` — підключено у `find_analogies` flow.
- 2 DRY-helper-и: `_get_asset` у роутері контексту,
  `_persist_assets_if_any` у роутері LLM.
- Вузький `ValidationError` замість `except Exception` у `_parse_assets`.

## [v1.1.0-design] — 2026-05-13

### Added — Design only (no code yet)
- **`docs/concept/v1.1-context-accumulation.md`** — повний дизайн-документ
  для наступного етапу, на основі статті Yaroslav Klochnyk «AI Agents
  in the SDLC: Why Task Automation Is No Longer Enough»
  (LinkedIn Pulse, 13.05.2026).
- Модель «двох результатів» для всіх LLM-функцій:
  `LLMResult[T] = (task_output, context_assets[])`.
- Сутність `ContextAsset` (типи: business_rule, failure_pattern, edge_case,
  operator_practice, training_gap, architectural_decision, deployment_lesson,
  acceptance_criterion) з lifecycle `draft → validated → deprecated`.
- Маппінг 1-в-1 на NATO LL Handbook 4 (Observation → LI → LL →
  Institutionalization) — стаття Клочника дала промислову назву тому,
  що NATO LL описує методологічно.
- Нові метрики flywheel: assets-per-task, validation-rate, reuse-rate,
  cycle-time reduction, **SmartnessIndex**.
- Етап 11 «Context Accumulation Layer» додано у `docs/roadmap.md`.
- ADR-007, ADR-008, ADR-009 додано в `docs/PROJECT.md` §6.
- `docs/concept/AAR_v2.md` §3.1 — анонсовано `ContextAsset` як 7-й
  довідник системи (з посиланням на v1.1 doc).
- `docs/PROJECT.md` оновлено: статус (v1.0 merged + release published),
  карта документації, plans для v1.1.

### Notes
Реалізація не входить у v1.0-пілот. Рекомендований перший фокус v1.1
після збору фідбеку з пілотного впровадження v1.0.

## [v1.0.0-pilot-ready] — 2026-05-11

### Added (Етап 10 — безпека, аудит, готовність до пілоту)
- **Append-only audit log з SHA-256 hash-chain** (A12):
  - Таблиця `audit_log` + міграція `0005_audit_log`.
  - `services/audit.append()` обчислює `entry_hash` = `SHA-256(canonical_json(
    action, actor, entity_type, entity_id, payload, prev_hash))`. Genesis
    = 64 нулі.
  - `services/audit.verify_chain()` повертає `(ok, checked, broken_at_id,
    message)` — будь-яка модифікація історичного рядка ламає ланцюг і
    показує id першого розбіжного запису.
  - Підключено до `POST /events` (`event.created`) та
    `POST /aar/cases` + `/aar/cases/{id}/close` (`case.created`/`case.closed`).
- **RBAC** через JWT bearer (`core/rbac.require_role(*roles)`):
  - У `development` — permissive (для тестів і локальної розробки).
  - Поза dev — потребує bearer-токен; `role`-claim повинен бути в
    дозволеному списку. 401 без токена, 403 при невідповідній ролі.
- **REST `/audit/*`**:
  - `GET /audit/log?action=&limit=` — захищений `Role.ADMIN/MANAGER/ANALYST`.
  - `GET /audit/verify` — захищений `Role.ADMIN/MANAGER`,
    повертає статус ланцюга.
- **Тести** (4): chain extends and verifies, tampering breaks chain
  (`entry_hash mismatch at id=1`), `/events` пише `event.created` у
  audit-log, `/audit/log` повертає 401 при `production`-environment
  без токена.
- **`docs/normative/iso-27001-controls.md`** — мапа Annex A контролів
  на код (A.5.15/5.18, A.8.3/5/15/16/24/32) + інфраструктурні
  контролі для пілоту (A.5.30, A.8.13/20/21/24/28).

### Acceptance — Roadmap §Етап 10
- ✓ Hash-chain цілісність валідується тестом.
- ✓ Маніпуляція рядком детектується.
- ✓ RBAC блокує неавтентифікований доступ у production.
- pending: розгортання `docker compose up` у замовника, restore-drill,
  звірка реквізитів № 440.

## [v0.10.0-integrations] — 2026-05-11

### Added (Етап 9 — універсальний інтеграційний шар)
- **Дворівнева архітектура**: один загальний REST/JSON-контракт +
  тонкі shape-адаптери на кожну цільову систему. Геопросторові дані
  передаються як **GeoJSON Point** (RFC 7946), щоб без перетворень
  споживались мапними клієнтами.
- **Підтримувані konnektor-kinds** (per policy, Оберіг **виключено** як
  таємну систему):
  - `generic` — pass-through `{event, data}`
  - `odin` — C2-envelope (`event_type / timestamp / actor / subject / outcome / geo`)
  - `delta` — GeoJSON FeatureCollection
  - `kropyva` — окремий GeoJSON Feature
  - `sap` — flat one-level PascalCase запис
- **Поле `location`** (GeoJSON Point) у `UsageEvent` + міграція
  `0004_integrations`.
- **Outbound webhooks**: `Subscription` (name, kind, target_url, secret,
  events[], headers, active) + аудит `Delivery` (status / response_code /
  attempts / error). HMAC-SHA256 підпис у `X-AAR-Signature`.
- **REST `/integrations/*`**:
  - `POST/GET/DELETE /subscriptions`, `GET /deliveries`
  - `GET /connectors` (явно перелічує `excluded: ["oberig"]`)
  - `POST /preview?kind=&event_id=` — попередній перегляд payload без
    реального POST
  - `POST /dispatch/{event_id}` — ручний fan-out з аудитом
  - `POST /inbound/events` — універсальний прийом нормалізованої події
    з будь-якої системи; ідемпотентний по `(source, external_id)`
  - `GET /events.geojson?date_from=&date_to=` — експорт у GeoJSON
    FeatureCollection для DELTA / Кропиви
- **Тести** (7): CRUD підписок, рендер payload (delta=GeoJSON, sap=flat),
  dispatch з мокнутим `_post` (HMAC-підпис коректний, response_code=202),
  inbound + ідемпотентність, GeoJSON-експорт, connectors виключає
  Оберіг.

## [v0.9.0-mod440-exports] — 2026-05-11

### Added (Етап 8 — нормативні експорти за наказом № 440)
- Залежність `python-docx>=1.1`.
- `services/mod440.py` — 4 форми:
  - **Узагальнююча відомість обліку** (Додаток 1 до п. 7 розділу II) —
    XLSX-знімок інвентаря по типах із залишком / надходженням / спожитим
    (success) / втратами / у ремонті.
  - **Журнал руху військового майна** — XLSX-лог подій за період
    із серійним №, типом, експлуатантом, результатом, кодом причини,
    підставою.
  - **Акт списання виробу** (безповоротна втрата) — DOCX за подією
    типу `lost`, поля: ЗАТВЕРДЖУЮ, №/дата, обставини, мат. відп. особа,
    члени комісії.
  - **Акт повернення в ремонт** — DOCX за подією типу `repair`, поля:
    №/дата, опис дефекту, здав / прийняв.
- REST `/exports/mod440/*`:
  - `GET /inventory.xlsx?unit_name&as_of`
  - `GET /movement.xlsx?date_from&date_to&unit_name`
  - `GET /loss-act/{event_id}.docx?unit_name&act_no&responsible_person&circumstances`
  - `GET /repair-act/{event_id}.docx?unit_name&act_no&sender&receiver&defect_description`
- Валідації типу події: акт списання вимагає `outcome=lost`, акт ремонту —
  `outcome=repair`; за невідповідності — `400`.
- Тести: бінарні підписи XLSX/DOCX (zip-magic `PK`), `Content-Disposition`,
  400 на спробі сформувати акт списання для успішної події.

## [v0.8.0-offline-pwa] — 2026-05-11

### Added (Етап 7 — offline-first PWA)
- **Серверна ідемпотентність**: поле `UsageEvent.client_event_id` (UUID,
  unique index) + міграція `0003_offline_idempotency`. `POST /events` із
  існуючим `client_event_id` повертає raніше створену подію без дублю.
- **IndexedDB-черга** (`apps/web/src/lib/db.ts`) через `idb`:
  store `event_queue`, key=`client_event_id`, індекс `by_status`.
- **Sync-логіка** (`apps/web/src/lib/sync.ts`):
  - `submitEvent()`: завжди enqueue → якщо online, відразу POST.
  - `flushQueue()`: відправляє всі `pending` події по черзі.
  - `installAutoSync()`: підписується на `online` event, авто-flush.
  - Кожна подія несе `client_event_id` — повторні спроби не створюють
    дублів на сервері.
- **UI**: нова сторінка `/event-form` з індикатором online/offline,
  списком черги, кнопкою «Синхронізувати зараз».
- **Тести** (vitest + `fake-indexeddb`):
  - 10 подій додано офлайн → 0 викликів `fetch`.
  - Online → flush: 10 викликів `fetch`, 10 `synced`; повторний flush — 0.

### Acceptance
Контрольна точка з roadmap Етапу 7 виконана: 10 подій офлайн → синхрон
без втрат і дублів.

## [v0.7.0-llm] — 2026-05-11

### Added (Етап 6 — LLM-автоматизація через Claude API)
- Залежність `anthropic>=0.40` + конфіг: `AAR_ANTHROPIC_API_KEY`,
  `AAR_LLM_DEFAULT_MODEL` (default `claude-sonnet-4-6`),
  `AAR_LLM_FAST_MODEL` (default `claude-haiku-4-5`), `AAR_LLM_ENABLED`.
- `services/llm.py`:
  - **A8** `classify_reason(text, catalog, kind)` — мапить вільнотекстовий
    опис у код причини (а–д / а–р) з `confidence` і `rationale`.
    Використовує Haiku 4.5 за замовч., output_config JSON-schema, prompt
    caching на словнику причин (ephemeral, cache_control на каталозі).
  - **A9** `draft_case_analysis(...)` — Markdown-драфт підсумкового
    аналізу менеджера (6 секцій: контекст / що сталося / чому / спрацювало /
    не спрацювало / рекомендації). Sonnet 4.6.
  - **A10** `find_analogies(query, knowledge_entries, top_k)` — ранжування
    записів `KnowledgeEntry` за релевантністю до нового кейсу через
    structured outputs.
- REST `/llm/*`:
  - `POST /llm/classify-reason` (підбирає словник за `kind`).
  - `POST /llm/cases/{id}/draft-analysis` (агрегує події оператора +
    індивідуальні звіти, передає у драфт).
  - `GET /llm/cases/{id}/analogies?top_k=3`.
- Усі ендпоінти повертають `503 LLM disabled` коли API ключ не
  сконфігуровано → ручні режими роботи завжди доступні.
- Тести (з `unittest.mock.patch`): 503 без ключа, мокована класифікація,
  виклик `draft_case_analysis` з правильним контекстом кейсу, порожні
  аналогії при порожній базі знань.

### Notes on Anthropic SDK usage
- Системні промпти структуровано як список `text`-блоків;
  `cache_control={"type": "ephemeral"}` стоїть на стабільному префіксі
  (каталог причин, instructions грейдера), а вільний користувацький текст
  іде у `messages[-1]` після останнього breakpoint.
- Логуються `usage.cache_read_input_tokens` /
  `usage.cache_creation_input_tokens` — для аудиту хіт-рейту.

## [v0.6.0-metrics] — 2026-05-11

### Changed (рефакторинг назв метрик до наукової нотації)
- Усі коефіцієнти перейменовано з українських абревіатур на латиницю
  з грецькими еквівалентами:
  - **Кеф → MSR (η)** Mission Success Rate = `N_success / N_sorties`
  - **Кеф_обсл → MSR_c (η_c)** Crew-adjusted MSR =
    `N_success / (N_sorties − N_loss_external − N_loss_manufacturer)`
  - **Кв_обсл → CLR (λ_c)** Crew Loss Rate = `N_crew_loss / N_sorties`
  - **Δ Кеф → ΔMSR (Δη)** у в.п.
- `TriggerType.KEFF_DROP` → `TriggerType.MSR_DROP` (значення в БД `msr_drop`).
- Перейменовано поля Pydantic-схем, локальних змінних, заголовків XLSX/PDF,
  тестових ключів. Українські описові підписи у звітах залишаються
  («Запущено», «Втрачено», «Ремонт», «Успіх», «Експлуатант»), коефіцієнти
  показуються як `η (MSR)`, `η_c (MSR_c)`, `λ_c (CLR)`, `Δη (в.п.)`.
- Новий документ [`docs/metrics.md`](docs/metrics.md) — єдине джерело
  істини щодо нотації, формул, порогів рейтингу і маппінгу старих назв.

### Migration note
Запис `TriggerType` зберігається у БД як рядок; чинна редакція використовує
`msr_drop`. Pre-existing dev/SQLite-бази не містять значень `keff_drop`
(жоден реальний прогін тригерів у проді не виконувався), тому міграція
даних не потрібна.

## [v0.5.0-aar-cases] — 2026-05-11

### Added (Етап 5 — AAR-кейси + тригери)
- `services/triggers`: engine із чотирма авто-тригерами T1–T4 (T5 = ручний):
  - **T1** Кеф_обсл оператора < 0.70 три доби поспіль → `keff_drop`.
  - **T2** Та сама причина (loss/repair) ≥ 3 разів за 7 діб → `repeated_reason`.
  - **T3** Серійний № отримав ≥ 2 ремонтів/втрат за 30 діб → `item_anomaly`.
  - **T4** Кеф підприємства впав > 10 в.п. day-over-day → `enterprise_drop`.
- Ідемпотентність: signature `[T#:key:date]` у заголовку кейсу, повторні
  запуски тригерів не дублюють кейси, а збільшують `skipped_existing`.
- REST `/aar/*`:
  - `POST /aar/cases` (ручний T5), `GET /aar/cases?status=&trigger=`,
    `GET /aar/cases/{id}`, `POST /aar/cases/{id}/close`.
  - `POST /aar/cases/{id}/reports` — індивідуальний звіт (6 блоків v1.0:
    что_сталося / що_спрацювало / що_ні / чому / зовнішні / що_змінити).
  - `POST /aar/cases/{id}/recommendations`,
    `PATCH /aar/recommendations/{id}` (proposed → in_progress → done →
    validated, з авто-`validated_at`).
  - `POST /aar/run-triggers?today=YYYY-MM-DD` — ручне ініціювання engine.
- CLI `python -m aar_api.scripts.run_triggers --date YYYY-MM-DD` для cron.
- Тести: T1 (3 дні × 5 пусків з Кеф_обсл=0.4), T3 (2 ремонти одного № за
  вікно), повний flow ручного кейсу (звіт → рекомендація → validate → close).

## [v0.4.0-monthly-report] — 2026-05-11

### Added (Етап 4 — місячна звітність + рейтинг)
- `services/monthly.build_monthly_report` агрегує події за вибраний місяць:
  Т.4 (інтегральні показники по операторах × типах виробів + Кеф / Кеф_обсл /
  Кв_обсл / Δ Кеф у в.п.), рейтинг експлуатантів за Кеф_обсл (категорії
  high/ok/needs_training, пороги 0.85 / 0.70), Т.7 (зони відповідальності
  — операторська / зовнішня / виробнича / unknown), Т.6 (тренди up/down/flat
  vs попередній місяць).
- Розширено `services/exports` функціями `monthly_report_to_xlsx/pdf`.
- REST: `GET /reports/monthly?year=...&month=...` (JSON / XLSX / PDF).
- CLI `python -m aar_api.scripts.monthly_report --year YYYY --month MM --out DIR`.
- Тести: точність розрахунку Кеф_обсл (6/7 при 1 зовнішній втраті),
  Δ Кеф (+25 в.п. між листопадом і груднем), тренд up, rank=1 для топ-1.

## [v0.3.0-daily-report] — 2026-05-11

### Added (Етап 3 — щоденна довідка)
- `services/reports.py`: агрегація подій по добі → `DailyReport` (Т.1
  зведення по парах експлуатант×тип, Т.2/Т.2.1 безповоротні втрати + розподіл
  за причинами, Т.3/Т.3.1 повернення в ремонт + розподіл, Кеф = success/launched).
- `services/exports.py`: XLSX (openpyxl) і PDF landscape A4 (reportlab).
- REST: `GET /reports/daily?date=YYYY-MM-DD` (JSON), `/daily.xlsx`, `/daily.pdf`.
- CLI `python -m aar_api.scripts.daily_report --date YYYY-MM-DD --out DIR`
  (за замовчанням — вчора, тека `./out`); для cron 23:59 на хост-системі.
- Тести: точна агрегація на синтетичному наборі (5/2 пусків E-01/E-02) + smoke
  на бінарні підписи XLSX/PDF.

### Changed
- `tests/conftest.py`: винесено autouse-фікстуру схеми БД, щоб усі тестові
  модулі бачили створені таблиці.

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
