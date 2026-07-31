from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.core.rbac import has_role, optional_claims, require_role
from aar_api.models.audit import AuditAction, AuditLog
from aar_api.models.user import Role
from aar_api.services import redaction
from aar_api.services.audit import verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: AuditAction
    actor: str | None
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str
    created_at: datetime


class ChainStatusOut(BaseModel):
    ok: bool
    checked: int
    broken_at_id: int | None
    message: str


@router.get(
    "/log",
    response_model=list[AuditEntryOut],
    dependencies=[Depends(require_role(Role.ADMIN, Role.MANAGER, Role.ANALYST))],
)
async def list_audit(
    action: AuditAction | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(optional_claims),
) -> list[AuditEntryOut]:
    """Read the chain. Anonymous-report originators are redacted below admin.

    This endpoint is open to ANALYST/MANAGER — the very people who read the
    testimony — and `payload` is returned verbatim, so writing the originator
    into the chain (the BUG-2 fix) would merely relocate the BUG-1 leak here.
    `services/redaction.audit_payload` is that mandatory companion; the stored
    row is untouched, so `entry_hash` still commits to the true originator and
    `verify_chain()` keeps working.
    """
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = list(await session.scalars(stmt))
    reveal = has_role(claims, Role.ADMIN)
    out: list[AuditEntryOut] = []
    for row in rows:
        entry = AuditEntryOut.model_validate(row)
        entry.payload = redaction.audit_payload(row.action, row.payload, reveal=reveal)
        out.append(entry)
    return out


@router.get(
    "/verify",
    response_model=ChainStatusOut,
    dependencies=[Depends(require_role(Role.ADMIN, Role.MANAGER))],
)
async def verify(session: AsyncSession = Depends(get_session)) -> ChainStatusOut:
    status = await verify_chain(session)
    return ChainStatusOut(
        ok=status.ok,
        checked=status.checked,
        broken_at_id=status.broken_at_id,
        message=status.message,
    )
