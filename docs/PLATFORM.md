# AAR Platform — Living Document

> **Призначення цього файлу.** Це єдиний living-документ для всіх — людей і
> AI-агентів — хто потрапляє на проєкт уперше. Тут описано: що ми будуємо,
> чому саме так (методологія), що вже зроблено, які рішення прийнято, що
> робиться зараз і що буде далі. Документ оновлюється з кожною зміною, що
> впливає на поведінку системи. Якщо ти агент — починай тут.

**Останнє оновлення:** 2026-06-10
**Поточна версія:** v1.1 (Context Accumulation Layer) + Wave 1 (NATO LL cycle)
**Активна гілка розробки:** `claude/equipment-tracking-system-3lB6U`
**Жива демо-версія:** https://yevhen-sh8.github.io/AAR/

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
«повний» (з абортами через РЕБ/погоду). У нас зараз — «вузький» від
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

---

## 5. Що НЕ зроблено і чому

| Робота | Стан | Чому відкладено |
|---|---|---|
| Workflow-двигун розсилки індивідуальних форм | планується (Wave 3) | Потребує черги + інтеграції з messenger; не блокує методологію |
| Дашборд мета-KPI циклу навчання (time-to-validation, recurrence rate) | планується (Wave 2) | Дані вже накопичуються в полях; UI — окрема порція |
| Уточнення MSR (вузький vs повний знаменник) | планується (Wave 2) | Потребує додавання поля `aborted` в UsageEvent — публічна зміна моделі |
| Cost-per-effect метрика | планується (Wave 2) | Потребує вартісних довідників |
| Неатрибутивний режим (TC 25-20 культура) | планується (Wave 3) | Дизайн RBAC уже підтримує; треба UI-toggle |
| Бекенд на хостингу для робочого додатку (не demo) | відкладено | Користувач вирішив поки лишити demo (Render/Fly/Railway — на потім) |
| Live integrations з DELTA/Kropyva | поза MVP | Потребує продуктивних ключів і нормативного дозволу |

---

## 6. Рішення (ADR-журнал, скорочено)

- **ADR-001** — Стек Python+FastAPI + React+Vite + Postgres. *Чому:* типобезпека,
  async-first, екосистема ML/LLM.
- **ADR-002** — Метрики в латиниці (η, η_c, λ_c). *Чому:* виноска до наукової
  літератури по дронах.
- **ADR-003** — Оберіг виключено з інтеграцій. *Чому:* таємна система, не
  ставиться в публічному компоненті.
- **ADR-004** — ISO/IEC 27001:2022 замість КСЗІ. *Чому:* запит замовника; ISO
  закриває майже всі КСЗІ-вимоги без проходження ДСТСЗІ-сертифікації для MVP.
- **ADR-007** — Дворезультатний LLM-патерн: `LLMResult[T] = (task, assets)`.
- **ADR-008** — Активи завжди стартують як `draft`. Ніколи auto-validate.
- **ADR-009** — `find_analogies` шукає тільки серед `validated`.
- **ADR-010 (новий, Wave 1)** — NATO state machine жорстка, forward-only.
  Регресія дозволена лише автоматичній автовалідації, не людині-вручну.
- **ADR-011 (новий, Wave 1)** — LLM draft зберігається в кейс. Поле `analysis`
  оновлюється тільки якщо було порожнім (не перетирає людський текст).

---

## 7. Roadmap наступних хвиль

**Хвиля 2 — Виміряти саме навчання (2–3 дні роботи)**
- Дашборд мета-KPI: time-to-validation, % LI→LL, recurrence rate, OPR-навантаження
- Розрізнення MSR-narrow / MSR-full (поле `aborted` на UsageEvent)
- Cost-per-effect
- UI для transitions (кнопки в CasesPage)
- LL-flywheel віджети на головному dashboard

**Хвиля 3 — Культура і поширення (3–5 днів)**
- Неатрибутивний режим (RBAC-toggle на видимість originator)
- Розсилка `IndividualReport` форм учасникам (push/email/messenger)
- Webhook на messenger при відкритті кейсу та при auto-validation
- Bulk-imports інтерфейс
- Видалити рудимент `KnowledgeEntry`

**Хвиля 4 — Робочий додаток (production)**
- Бекенд на Render/Fly з Postgres
- TLS, secrets-vault, JWT-rotation
- Резервне копіювання + restore-drill
- Pilot у однієї військової частини

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
| Як bootstrapнути локально | `CLAUDE.md` § Build & Test Commands |

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
