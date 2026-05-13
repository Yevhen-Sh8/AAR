"""Append-only audit chain.

The chain anchor is the all-zero hex string (genesis). Each entry computes
`SHA-256(canonical_json(action, actor, entity_type, entity_id, payload, prev_hash))`
and stores both `prev_hash` and the resulting `entry_hash`. Verification walks
the table in `id` order and recomputes the chain; any deviation returns the
offending id.

Critical: the audit table is intentionally NOT updateable from application code.
At deploy time, lock it down with a DB-level rule (Postgres):
    REVOKE UPDATE, DELETE ON audit_log FROM aar_app;
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.models.audit import AuditAction, AuditLog

GENESIS = "0" * 64


def _hash(
    action: AuditAction,
    actor: str | None,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    prev_hash: str,
) -> str:
    canonical = json.dumps(
        {
            "action": action.value,
            "actor": actor,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "prev_hash": prev_hash,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


async def _latest_hash(session: AsyncSession) -> str:
    row = await session.scalar(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(1)
    )
    return row.entry_hash if row else GENESIS


async def append(
    session: AsyncSession,
    *,
    action: AuditAction,
    entity_type: str,
    entity_id: str | int,
    payload: dict[str, Any] | None = None,
    actor: str | None = None,
) -> AuditLog:
    prev = await _latest_hash(session)
    payload = payload or {}
    entry_hash = _hash(action, actor, entity_type, str(entity_id), payload, prev)
    entry = AuditLog(
        action=action,
        actor=actor,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
        prev_hash=prev,
        entry_hash=entry_hash,
    )
    session.add(entry)
    await session.flush()
    return entry


@dataclass(frozen=True)
class ChainStatus:
    ok: bool
    checked: int
    broken_at_id: int | None
    message: str


async def verify_chain(session: AsyncSession) -> ChainStatus:
    rows = list(await session.scalars(select(AuditLog).order_by(AuditLog.id)))
    expected_prev = GENESIS
    for row in rows:
        if row.prev_hash != expected_prev:
            return ChainStatus(
                ok=False,
                checked=row.id,
                broken_at_id=row.id,
                message=f"prev_hash mismatch at id={row.id}",
            )
        recomputed = _hash(
            row.action, row.actor, row.entity_type, row.entity_id, row.payload,
            row.prev_hash,
        )
        if recomputed != row.entry_hash:
            return ChainStatus(
                ok=False,
                checked=row.id,
                broken_at_id=row.id,
                message=f"entry_hash mismatch at id={row.id}",
            )
        expected_prev = row.entry_hash
    return ChainStatus(
        ok=True, checked=len(rows), broken_at_id=None, message="chain ok"
    )
