# DEPLOY — робочий додаток у проді (Wave 4)

> Мета: перетворити demo на **справді робочий додаток** — з реальним записом
> даних, базою, імпортом, AAR-кейсами. Усе керується з браузера, локально нічого
> ставити не треба.

## TL;DR — найшвидший шлях (Render Blueprint, ~5 хв, безкоштовно)

1. Відкрий <https://dashboard.render.com> → зареєструйся через GitHub.
2. **New → Blueprint**.
3. Обери репозиторій `yevhen-sh8/aar` і потрібну гілку.
4. Render прочитає `render.yaml` у корені й покаже, що створить:
   - **aar-db** — безкоштовний Postgres 16;
   - **aar-api** — бекенд (Docker, FastAPI);
   - **aar-web** — фронтенд (статичний сайт, React PWA).
5. Натисни **Apply**. Перший білд ~5 хв.
6. Бекенд при старті сам:
   - застосує всі міграції (`alembic upgrade head`);
   - засіє синтетичні дані (ідемпотентно — повторно не дублює).
7. Відкрий URL сервісу **aar-web** (вигляду `https://aar-web.onrender.com`) —
   повноцінний робочий додаток. Кнопки «створити подію», «імпорт»,
   «валідувати» тепер реально пишуть у БД.

Готово. Жодного рядка в терміналі.

### Вхід у застосунок (Wave 5)

Додаток закритий за паролем (окрім GitHub Pages demo — там логіну немає).
Бекенд сам створює адміністратора при старті:

- **Email:** значення `AAR_ADMIN_EMAIL` (за замовчуванням `admin@aar.local`).
- **Пароль:** значення `AAR_ADMIN_PASSWORD` (за замовчуванням `aar-admin-2026`,
  якщо змінну не задано).

**Щоб змінити пароль:** Render → сервіс **aar-api** → **Environment** →
онови `AAR_ADMIN_PASSWORD` → **Save Changes**. Render автоматично
передеплоїть сервіс, і при наступному старті пароль адміністратора
синхронізується з новим значенням — це працює при **кожному** рестарті
(не лише при першому створенні), тож зміна пароля через дашборд завжди
діє одразу після редеплою.

### Увімкнути AI-функції (опційно)

LLM-чернетки аналізу, класифікація причин, пошук аналогій — вимкнені за
замовчуванням (щоб не вимагати ключа). Щоб увімкнути:

1. Render → сервіс **aar-api** → **Environment**.
2. Додай `AAR_ANTHROPIC_API_KEY` = твій ключ Anthropic.
3. Зміни `AAR_LLM_ENABLED` на `true`.
4. **Manual Deploy → Deploy latest commit** (або зачекай авто-деплой).

## Що відбувається під капотом

| Компонент | Як деплоїться | Нюанси free-плану |
|---|---|---|
| Postgres | `databases:` у `render.yaml`, plan free | 90 днів, потім потрібен новий free-інстанс або платний |
| API (FastAPI) | Docker з `apps/api/Dockerfile`; entrypoint `start.sh` | Засинає після 15 хв простою; перший запит після сну ~30–60 с |
| Web (React) | Статичний сайт, build з `VITE_API_BASE` на URL API | CDN, не засинає |

**`start.sh`** (entrypoint контейнера API) робить три речі:
```sh
alembic upgrade head                 # міграції
[ "$AAR_SEED_ON_START" = "true" ] && python -m aar_api.scripts.seed
exec uvicorn aar_api.main:app --host 0.0.0.0 --port $PORT
```

**Нормалізація БД-URL.** Render видає `postgresql://…` без асинхронного драйвера.
`core/config.py` автоматично конвертує його в `postgresql+asyncpg://…` (а для
синхронного Alembic драйвер відрізається в `alembic/env.py`). Той самий
`AAR_DATABASE_URL` працює і локально, і в проді.

**CORS.** `AAR_CORS_ORIGINS` — явний allow-list (через кому): `aar-web` +
GitHub Pages demo. Якщо `AAR_CORS_ORIGINS` містить `*`, бекенд перемикається
в bullet-proof pilot-режим (echo `*` без credentials) — зручно на самому
старті, коли фінальний домен ще невідомий, але для проду тримай явний список.

**Security headers.** Кожна відповідь API несе `X-Content-Type-Options`,
`X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`,
`Strict-Transport-Security` і `Content-Security-Policy` (окрема, м'якша
політика на `/docs`/`/redoc`, бо Swagger UI тягне бандл з CDN).

**Rate limiting входу.** `/auth/login` обмежений — за замовчуванням 20 спроб
на 5 хвилин з одного IP (`AAR_LOGIN_RATE_LIMIT_ATTEMPTS` /
`AAR_LOGIN_RATE_LIMIT_WINDOW_SECONDS`). Ліміт живе в пам'яті процесу (без
Redis) — скидається при рестарті контейнера; достатньо для одного
pilot-інстансу, не для розподіленої атаки.

## Змінні середовища API (префікс `AAR_`)

| Змінна | Призначення | Прод-значення |
|---|---|---|
| `AAR_DATABASE_URL` | Async Postgres DSN | з `aar-db` (auto) |
| `AAR_JWT_SECRET` | Підпис JWT | генерується Render |
| `AAR_ENVIRONMENT` | `development`/`production` | `production` |
| `AAR_SEED_ON_START` | Засіяти демо-дані на старті | `true` (вимкни після пілота) |
| `AAR_CORS_ORIGINS` | Дозволені origin'и (через кому) | `https://yevhen-sh8.github.io` |
| `AAR_CORS_ORIGIN_REGEX` | Regex дозволених origin'ів | `https://.*\.onrender\.com` |
| `AAR_LLM_ENABLED` | Увімкнути LLM | `false` (поки без ключа) |
| `AAR_ANTHROPIC_API_KEY` | Ключ Anthropic | (порожньо; задай вручну) |
| `AAR_ADMIN_EMAIL` | Email bootstrap-адміна | `admin@aar.local` |
| `AAR_ADMIN_PASSWORD` | Пароль bootstrap-адміна (синхронізується при кожному старті) | задай вручну в дашборді |
| `AAR_LOGIN_RATE_LIMIT_ATTEMPTS` | Спроб входу на вікно | `20` |
| `AAR_LOGIN_RATE_LIMIT_WINDOW_SECONDS` | Тривалість вікна (с) | `300` |

## Альтернатива: локально через Docker Compose

Якщо потрібен повний контур у себе (on-prem):
```bash
cd infra
docker compose up
# API: http://localhost:8000/api · Web: http://localhost:8080
```
Compose сам піднімає Postgres + Redis + api + web і застосовує міграції.

## Альтернатива: Fly.io / Railway

`render.yaml` специфічний для Render, але `apps/api/Dockerfile` + `start.sh`
платформонезалежні. Для Fly: `fly launch` у `apps/api`, додай Postgres
(`fly postgres create`), прокинь `AAR_DATABASE_URL`, вистав `PORT` (Fly робить
це сам). Той самий entrypoint застосує міграції й підніме сервер.

## Підключити наявний GitHub Pages demo до живого бекенду

Demo на Pages за замовчуванням read-only (mock-дані). Щоб він ходив у живий
Render-бекенд: у `.github/workflows/pages.yml` додай до build-кроку
`VITE_API_BASE=https://aar-api.onrender.com/api` і прибери `VITE_DEMO=true`.
Тоді Pages-фронтенд стане живим клієнтом прод-API (CORS уже дозволяє
`github.io`). Рекомендація: лиши Pages як demo-вітрину, а робочий додаток
тримай на `aar-web.onrender.com` — менше плутанини.

## Перевірка після деплою

1. `https://aar-api.onrender.com/health/live` → `{"status":"ok",...}`.
2. `https://aar-api.onrender.com/health/ready` → `{"status":"ready"}` (БД жива).
3. Відкрий aar-web → Дашборд показує засіяні дані.
4. Подай подію → онови Дашборд → число змінилось (реальний запис у БД).
5. Відкрий кейс → «Згенерувати аналіз (LLM)» (якщо ключ заданий) → аналіз
   зберігається в кейсі.

## Резервне копіювання (Wave 5, тільки браузер)

Безкоштовний план Postgres на Render **не робить автоматичних бекапів** і
**видаляється через 90 днів**. Оскільки цей деплой керується виключно з
браузера (без терміналу), звичайний `pg_dump` тут не варіант день-у-день.

**Що є зараз:** Налаштування → «Резервна копія» → кнопка «Завантажити
резервну копію (JSON)» — авторизований (роль admin) ендпойнт
`GET /admin/export` віддає повний JSON-знімок робочих таблиць
(довідники, вироби, події, AAR-кейси, рекомендації, контекст-активи,
користувачі без хешів паролів) як файл для завантаження в браузер.
Рекомендація: раз на тиждень під час пілоту.

**Чого це НЕ замінює:** це не point-in-time recovery і не автоматичний
процес. Для реального проду — онови план Postgres на Render до платного
(додає щоденні бекапи + PITR) або постав окремий cron, що регулярно тягне
`/admin/export` і зберігає файл десь поза Render.

## Безпека прод-контуру (ISO/IEC 27001)

Перед бойовим використанням (не пілотом) — див.
`docs/normative/iso-27001-controls.md`. Ключове, що НЕ покрито free-деплоєм і
потребує рішення:
- шифрування at-rest (Render шифрує диски; для суверенного контуру — LUKS/TDE);
- справжній point-in-time backup/restore (платний план Postgres — JSON-експорт
  вище лише супровідна страховка, не заміна);
- ротація секретів і JWT;
- приватна мережа / VPN-доступ замість публічного URL.
