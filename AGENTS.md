# AGENTS.md — entry point for AI agents

This file is the tool-neutral bootstrap. If you are an AI agent (Claude Code,
Cursor, Codex, Aider, Windsurf, or anything else) landing on this repo: read
this in full, then go to the two files it points to.

## What this project is, in one sentence

A defense-grade AAR (After Action Review) platform that does per-serial-number
equipment tracking + structured Lessons Learned per NATO LLH4, with an
auto-validation loop that closes the "lessons observed ≠ lessons learned" gap.

## What to read first

1. **`docs/PLATFORM.md`** — the living document. Vision, methodology,
   architecture, ADR journal, what's done, what's next, where to read what.
   **Always read this fully before making any non-trivial change.**
2. **`CLAUDE.md`** — repo-level conventions, commands, test/lint instructions.
   Works the same regardless of which agent you are.

Everything below is the minimum subset you need to act safely.

## Repo layout

```
apps/api/          FastAPI + SQLAlchemy 2 (async) + Alembic
apps/web/          React 18 + Vite + TypeScript PWA
infra/             Docker Compose (Postgres 16, Redis 7, api, web)
packages/shared/   Shared classifiers JSON
docs/              Living docs — PLATFORM.md is the master
.claude/skills/    Project-level Claude Code skills (e.g. /workflows)
```

## Build & test (canonical)

```bash
# Backend (from apps/api/)
pip install -e ".[dev]"
ruff check . && mypy aar_api && pytest -q

# Frontend (from apps/web/)
npm install
tsc -b && npm run build && npm test
```

Tests use in-memory SQLite — no Postgres needed locally.

## Development rules (non-negotiable)

1. **Branch:** all work goes to `claude/equipment-tracking-system-3lB6U`.
   Never push to `main` directly.
2. **Any data model change → Alembic migration + tests + update
   `docs/PLATFORM.md` §4 (status) and §6 (ADR journal if architectural).**
3. **NATO state machine for AAR cases is enforced** — see
   `aar_api/models/aar.py::ALLOWED_TRANSITIONS`. Only forward moves;
   regression is reserved for the auto-validation engine.
4. **LLM functions return `LLMResult[T] = (task_output, context_assets[])`.**
   Assets always start as `draft`. Never auto-validate (ADR-008).
5. **Analogy search only over `validated` context assets** (ADR-009).
6. **Оберіг is excluded from integrations** — classified system, policy
   decision (ADR-003).
7. **Audit hash-chain is append-only.** Every domain action that mutates
   state must call `services.audit.append(...)`.
8. **ISO/IEC 27001:2022, not КСЗІ** — see `docs/normative/iso-27001-controls.md`.

## Decision protocol

- Reversible local edit (code, test, doc) → just do it, then verify with the
  build/test commands above.
- Schema change, new API surface, removal of a feature → mention to user
  first; consider an ADR entry in `docs/PLATFORM.md` §6.
- Anything affecting `main`, secrets, prod infra, or external integrations →
  ask user explicitly before acting.

## Demo vs live

Frontend has a baked-in demo mode (`VITE_DEMO=true`) that swaps the API base
to static `apps/web/public/mock/*.json`. GitHub Pages deploys this:
https://yevhen-sh8.github.io/AAR/

Backend is currently not deployed — by user decision, demo is enough for now.
When backend deployment is requested, see `docs/PLATFORM.md` §7 (Wave 4) for
the plan.

## Where to update what

| Type of change | Files to touch |
|---|---|
| New model / migration | `apps/api/aar_api/models/`, `apps/api/alembic/versions/NNNN_*.py`, tests, `docs/PLATFORM.md` |
| New endpoint | router file, schema file, test, `docs/PLATFORM.md` §8 (map) |
| New UI page | `apps/web/src/pages/`, `App.tsx` (route + nav), mock JSON, `docs/PLATFORM.md` §4 |
| New automation rule | `apps/api/aar_api/services/`, tests, `docs/automation.md`, `docs/PLATFORM.md` |
| Normative / methodology change | `docs/normative/`, `docs/PLATFORM.md` §3, §6 |
| New ADR | `docs/PLATFORM.md` §6 |

## When you finish

1. Run lint + tests for the part you touched.
2. Update `docs/PLATFORM.md` if your change affected behavior (this is a
   hard rule, not a polite suggestion).
3. Commit with a descriptive message; push to the development branch above.
4. If there is an open PR for that branch, your push joins it. If not,
   create a draft PR.

## Things that look like rules but are not

- Style: ruff line length 100, default ruff E/F/I/B/UP. No bikeshedding.
- Comments: write *why*, not *what*. Don't add comments that restate the code.
- Tests: cover the new behavior, not implementation detail. Aim for one test
  per externally visible decision.

## How to ask for help

If something blocks you that the user must decide (irreversible action, scope
beyond the branch, missing input) — stop and ask. Don't guess on irreversible
moves.

---

*This file is intentionally short. The real story is in `docs/PLATFORM.md`.*
