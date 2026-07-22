# PROJECT.md — живий довідник проєкту AAR

> Цей файл — **єдина точка входу для щоденної роботи з проєктом**. Тримайте
> його актуальним: після будь-якої суттєвої зміни (концепція, архітектура,
> ролі, етап дорожньої карти, нормативка, рішення) — оновлюйте відповідний
> розділ і додавайте запис у `CHANGELOG.md`.

## 1. Що це за проєкт

Цифрова платформа **AAR (After Action Review)** — система аналізу і
накопичення досвіду. Розширена концепція v2.0 включає окремий модуль
**«Облік і ефективність виробів»** (пономерний облік, причини а–д / а–р,
η (MSR), рейтинг експлуатантів, авто-тригери AAR-кейсів).

## 2. Куди дивитися (карта документації)

| Питання | Файл |
|---|---|
| Філософія, що ми будуємо | [`docs/concept/AAR_v2.md`](concept/AAR_v2.md) |
| План v1.1 (Context Accumulation Layer) | [`docs/concept/v1.1-context-accumulation.md`](concept/v1.1-context-accumulation.md) |
| Що саме і коли робимо | [`docs/roadmap.md`](roadmap.md) |
| Які процеси автоматизуються | [`docs/automation.md`](automation.md) |
| Метрики (MSR, MSR_c, CLR), нотація | [`docs/metrics.md`](metrics.md) |
| Як виглядає щоденна довідка | [`docs/forms/daily-template.md`](forms/daily-template.md) |
| Як виглядає місячна звітність | [`docs/forms/monthly-template.md`](forms/monthly-template.md) |
| Нормативна база | [`docs/normative/README.md`](normative/README.md) |
| Наказ № 440 у деталях | [`docs/normative/mod-440.md`](normative/mod-440.md) |
| NATO LL ↔ AAR | [`docs/normative/nato-ll.md`](normative/nato-ll.md) |
| Що ще не покрито | [`docs/normative/gap-analysis.md`](normative/gap-analysis.md) |
| ISO/IEC 27001 контролі | [`docs/normative/iso-27001-controls.md`](normative/iso-27001-controls.md) |
| Як розгорнути робочий контур | [`docs/DEPLOY.md`](DEPLOY.md) |
| Як запустити пілот (чек-лист, базова лінія) | [`docs/PILOT.md`](PILOT.md) |
| Швидкий старт за ролями (що кому тиснути) | [`docs/QUICKSTART_ROLES.md`](QUICKSTART_ROLES.md) |
| Замір «до/після» для рішення про постачання | [`docs/BEFORE_AFTER_TEMPLATE.md`](BEFORE_AFTER_TEMPLATE.md) |
| Увімкнення ШІ + які дані виходять у LLM-API | [`docs/AI_ENABLEMENT.md`](AI_ENABLEMENT.md) |
| Історія змін | [`CHANGELOG.md`](../CHANGELOG.md) |

## 3. Поточний статус

- **Версія концепції**: v2.0
- **Версія продукту**: **v1.8.0** (єдина для api/web — `pyproject.toml`,
  `aar_api/__init__.py`, `SettingsPage.tsx`).
- **Стан**: v1.0/v1.1 + Хвилі 1–10 змерджено в `main` — pilot-ready.
  Детальний перелік реалізованого — `docs/PLATFORM.md` §4; історія — `CHANGELOG.md`.
- **Найближчі дії**:
  - Пілот у замовника (див. `docs/PILOT.md`), увімкнення ШІ за потреби
    (`docs/AI_ENABLEMENT.md`), замір «до/після» (`docs/BEFORE_AFTER_TEMPLATE.md`).
  - Бэклог: Signal-канал, live DELTA/Kropyva, прод-хардеринг (at-rest/PITR).
- **Що вже є (стисло)**:
  - Дворівнева модель (події → AAR-кейси, цикл NATO), тригери T1–T5,
    авто-валідація рекомендацій, Context Accumulation Layer (ADR-007/008/009),
    проактивні сигнали, брифінг місії + ШІ-синтез, цикл навчання (мета-KPI),
    геокарта подій, CRUD довідників (admin), audit hash-chain.
  - 10 Alembic-міграцій (`0001`–`0010`). `KnowledgeEntry` видалено (Хвиля 3).
  - Інтеграції: generic/ODIN/DELTA/Kropyva/SAP + Telegram (**Оберіг виключено**).
  - JWT-авторизація (PyJWT/HS256), rate-limit логіну, security-заголовки,
    admin JSON-бекап.
  - PWA offline-first; CI зелений (ruff/mypy/pytest/vitest/build).

## 4. Стек і середовище (узгоджено)

| Шар | Технологія |
|---|---|
| Бекенд | Python 3.12 + FastAPI + SQLAlchemy + Alembic |
| База даних | PostgreSQL 16 |
| Кеш / черга | Redis 7 |
| Фронт | React 18 + Vite + TypeScript |
| PWA | Workbox, IndexedDB, service worker |
| LLM | Claude API (Sonnet 4.6 default, Haiku 4.5 fallback), prompt caching |
| Розгортання | Docker Compose, on-prem у замовника |
| CI | GitHub Actions (ruff, mypy, pytest, vitest, build) |
| Безпека | ISO/IEC 27001:2022, ISO/IEC 27002:2022 |

## 5. Ролі у системі

| Роль | Відповідальність |
|---|---|
| Учасник / експлуатант | Подає індивідуальні звіти та пономерні події |
| Аналітик підприємства | Формує щоденні та місячні довідки |
| Менеджер AAR | Узагальнює кейси, підтверджує авто-тригери |
| Адміністратор | Веде довідники, керує доступом |
| Системний інтегратор | Налаштовує CSV/REST джерела даних |

## 6. Ключові архітектурні рішення (ADR-light)

| # | Рішення | Чому |
|---|---|---|
| ADR-001 | Python + FastAPI для бекенду | Швидкий старт, інтеграція з Claude SDK, аналітика на pandas |
| ADR-002 | PWA замість нативного мобільного | Один кодбейс, offline-first, простіше розгортання |
| ADR-003 | Дворівнева модель (події + кейси) | Розділяє кількісний і якісний шар, як радить NATO LL |
| ADR-004 | LLM-класифікація з людською валідацією | Не довіряємо моделі сліпо; зберігаємо первинний текст |
| ADR-005 | Append-only events + hash-chain | Цілісність обліку (ISO 27001 A.8) і вимоги наказу № 440 |
| ADR-006 | ISO 27001/27002 замість КСЗІ | Актуальна практика 2025–2026 |
| ADR-007 | Модель «двох результатів» LLM (Task Output + Context Asset) | Реалізує NATO LL цикл O→LL→Institutionalization; стаття Klochnyk 2026 |
| ADR-008 | `ContextAsset.status` default = `draft`, validation тільки людиною | Уникнення «scaling mistakes» |
| ADR-009 | `find_analogies` шукає тільки серед `validated` активів | shared context ≠ shared confusion |

## 7. Правила підтримки документації

1. **Будь-яка зміна концепції / архітектури** → оновити відповідний файл +
   додати запис у `CHANGELOG.md` із датою і коротким описом.
2. **Нове рішення** (стек, інтеграція, обмеження) → додати рядок у §6 ADR.
3. **Зміна етапу** → оновити §3 «Поточний статус» і `docs/roadmap.md`.
4. **Новий нормативний акт** → додати у `docs/normative/README.md` і за
   потреби — у `gap-analysis.md`.
5. **Кожен PR**, що змінює поведінку, має оновлювати `PROJECT.md` або явно
   зазначати «документація не потребує змін».

## 8. Як швидко увійти у проєкт (для нового розробника)

1. Прочитати цей файл.
2. Прочитати [`docs/concept/AAR_v2.md`](concept/AAR_v2.md) — 15 хвилин.
3. Переглянути [`docs/roadmap.md`](roadmap.md) — поточний етап.
4. Запустити `docker compose up` (буде доступно після Етапу 1).
5. Відкрити `apps/web` у браузері, `apps/api/docs` — Swagger.

## 9. Контакти / власники розділів

| Розділ | Власник |
|---|---|
| Концепція, нормативка | (заповнити) |
| Бекенд / API | (заповнити) |
| Фронт / PWA | (заповнити) |
| LLM / автоматизація | (заповнити) |
| Безпека | (заповнити) |
