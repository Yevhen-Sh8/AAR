# ISO/IEC 27001:2022 — мапа реалізованих контролів

Як платформа AAR покриває контрольні заходи з Annex A. Стовпчик «Реалізація»
посилається на конкретний код / етап. Невпроваджені контролі позначені як
TODO для пілотного впровадження (інфраструктурні рішення замовника).

## Покрито у коді

| Anneх A | Назва | Реалізація |
|---|---|---|
| **A.5.15** | Контроль доступу | RBAC через JWT bearer + `core/rbac.require_role(*roles)`; ролі `Role` (participant/analyst/manager/admin/integrator). |
| **A.5.18** | Права доступу | Дозволи прописані на рівні роутерів через `Depends(require_role(...))`. |
| **A.8.3** | Управління доступом до інформації | Усі чутливі ендпоінти (`/audit/*`) вимагають `Role.ADMIN` або `Role.MANAGER`. |
| **A.8.5** | Безпечна автентифікація | Bearer JWT; fail-fast на дефолтному `AAR_JWT_SECRET` поза dev-середовищем (`main.py`). |
| **A.8.15** | Логування | Append-only `AuditLog` з SHA-256 hash-chain (`services/audit.py`). |
| **A.8.16** | Моніторинг активностей | `/audit/log` + `/audit/verify`; запис подій від `events`, `aar/cases`, `recommendations`, `integrations`. |
| **A.8.24** | Криптографія | HMAC-SHA256 підпис вебхуків (`X-AAR-Signature`); SHA-256 у hash-chain аудиту. |
| **A.8.32** | Управління змінами | Alembic-міграції з версіонуванням; усі зміни схеми ревізуються через PR. |

## Інфраструктурні контролі (виконуються на пілоті замовника)

| Anneх A | Назва | Як забезпечити |
|---|---|---|
| **A.5.30** | ICT-готовність до безперервності | Резервне копіювання Postgres (`pg_basebackup` + WAL), регулярний restore-drill. |
| **A.8.13** | Резервне копіювання | Щодобовий бекап БД + offsite-копія; ретенція 30 днів. |
| **A.8.20** | Безпека мереж | TLS 1.3 на nginx; внутрішня мережа Docker; egress по allow-list. |
| **A.8.21** | Безпека мережевих сервісів | nginx security headers (CSP, X-Frame-Options, Referrer-Policy) — `apps/web/nginx.conf`. |
| **A.8.24 (at-rest)** | Шифрування дисків | LUKS на host-системі / TDE Postgres / pgcrypto для PII. |
| **A.8.28** | Безпечне кодування | ruff + mypy strict-режим у CI; залежності перевіряються `pip-audit` (TODO). |

## Hash-chain аудиту — деталі

Кожен запис у `audit_log`:

```
entry_hash = SHA-256(canonical_json({
    action, actor, entity_type, entity_id, payload, prev_hash
}))
```

- **Genesis**: `prev_hash = "0"*64` для першого запису.
- **Verification**: `/audit/verify` повертає `ok=true` або `broken_at_id` першого
  рядка, що не відповідає очікуваному хешу.
- **БД-рівень**: на проді обов'язково
  `REVOKE UPDATE, DELETE ON audit_log FROM aar_app;` — додаток ніколи не
  має прав модифікувати або видаляти історичні записи. Тільки `INSERT`.

## Pilot acceptance checklist (Етап 10)

- [x] Hash-chain цілісність валідується ендпоінтом `/audit/verify`.
- [x] Маніпуляція з історичним рядком виявляється тестом `test_tampering_breaks_chain`.
- [x] RBAC блокує неавтентифікований доступ у `production` (тест
      `test_rbac_blocks_unauthenticated_in_prod`).
- [ ] Розгортання за `docker compose up` із прод-конфігом (на пілоті).
- [ ] Restore-drill із бекапу (на пілоті).
- [ ] Звірка реквізитного складу експортів № 440 з документами замовника (на пілоті).
