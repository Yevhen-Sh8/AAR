# RELEASE.md — процедура релізу AAR

Інструкція для maintainer'а проєкту. Версія тегу пишеться як `vMAJOR.MINOR.PATCH`
(SemVer). Початковий реліз — `v1.0.0`.

## 1. Підготовка

Переконатись, що `main` чисто збирається і всі тести проходять:

```bash
cd apps/api
ruff check . && mypy aar_api && pytest -q
cd ../web
npx tsc -b && npx vitest run
```

Оновити `docs/PROJECT.md` (поточний етап) і додати запис у `CHANGELOG.md`
під заголовком `## [vX.Y.Z-name] — РРРР-ММ-ДД`.

## 2. Створення тегу

Анотований тег з повним описом релізу (тіло береться з найновішого блоку
CHANGELOG.md):

```bash
git tag -a v1.0.0 -m "AAR v1.0.0 — pilot-ready"
git push origin v1.0.0
```

Якщо тег уже існує локально (наприклад, агент створив, але не зміг запушити):

```bash
git tag --list "v*"        # переконатись, що тег є
git push origin v1.0.0     # піде під вашою авторизацією
```

## 3. GitHub Release

1. Відкрити https://github.com/Yevhen-Sh8/AAR/releases → **Draft a new release**.
2. **Choose a tag** → вибрати `v1.0.0`.
3. **Release title** → `AAR v1.0.0 — pilot-ready` (або відповідне).
4. **Generate release notes** — GitHub автоматично складе нотатки з PR-комітів
   між попереднім тегом і поточним. Очистити / скоригувати.
5. Скопіювати релевантний блок з `CHANGELOG.md` у тіло.
6. Якщо це pre-release (alpha/beta/rc) — поставити галочку **Set as a pre-release**.
7. **Publish release**.

## 4. Pilot acceptance (для v1.0.0 — на боці замовника)

Після релізу:

- [ ] `docker compose up` із прод-конфігом (`AAR_ENVIRONMENT=production`,
      заповнені `AAR_JWT_SECRET` та `AAR_ANTHROPIC_API_KEY`).
- [ ] Restore-drill із бекапу Postgres.
- [ ] Заміна абстрактних класифікаторів у `packages/shared/classifiers.json`
      на реальні коди причин а–д / а–р.
- [ ] Звірка реквізитного складу експортів № 440 з документами в/ч.
- [ ] DB-lockdown аудит-таблиці:
      `REVOKE UPDATE, DELETE ON audit_log FROM aar_app;`

## 5. Наступні версії

| Тип зміни | Bump |
|---|---|
| Виправлення без зміни поведінки | PATCH (1.0.0 → 1.0.1) |
| Нова функція з backwards-compat | MINOR (1.0.0 → 1.1.0) |
| Breaking change у API чи моделі даних | MAJOR (1.0.0 → 2.0.0) |
| Pre-release | `-alpha.N`, `-beta.N`, `-rc.N` |

## 6. Якщо реліз потрібно відкликати

Видалити тег не можна (історичний артефакт), натомість випустити patch:

```bash
git revert <bad-commit>
git tag -a v1.0.1 -m "Revert <reason>"
git push origin main v1.0.1
```

У GitHub Release → знайти проблемний реліз → **Mark as draft** або
**Set as pre-release** із поясненням у тілі.

## Примітка по агентським сесіям

Якщо реліз готує агент (Claude Code/Web), push тегів через агентський gateway
може блокуватися (HTTP 403 на `refs/tags/*`). У такому разі агент створює тег
**локально**, описує його в `CHANGELOG.md` та PR, а maintainer виконує
`git push origin <tag>` під своєю авторизацією. Це нормальний робочий цикл.
