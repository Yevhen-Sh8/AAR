"""Dictionaries — read for everyone, write (create/update/delete) for admins.

Codes are the stable identifiers referenced by events, items and cases, so:
- `code` is unique and immutable after creation (edit name/zone/cost instead);
- a delete is refused with 409 while any record still references the entry
  (we never orphan events by removing a classifier out from under them).

Every write is recorded in the append-only audit hash-chain.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.core.rbac import require_role
from aar_api.models.aar import AARCase
from aar_api.models.audit import AuditAction
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason
from aar_api.models.event import Item, UsageEvent
from aar_api.models.user import Role
from aar_api.schemas.dictionaries import (
    ItemTypeIn,
    ItemTypeOut,
    ItemTypeUpdate,
    OperatorIn,
    OperatorOut,
    OperatorUpdate,
    ReasonIn,
    ReasonOut,
    ReasonUpdate,
)
from aar_api.services.audit import append as audit_append

router = APIRouter(prefix="/dictionaries", tags=["dictionaries"])

_admin = Depends(require_role(Role.ADMIN))


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

async def _ensure_unique_code(session: AsyncSession, model: Any, code: str) -> None:
    exists = await session.scalar(select(model.id).where(model.code == code))
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"code '{code}' already exists",
        )


async def _get_or_404(session: AsyncSession, model: Any, obj_id: int) -> Any:
    obj = await session.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return obj


async def _refuse_if_referenced(
    session: AsyncSession, *ref_counts: Any, label: str
) -> None:
    """Each arg is a scalar-count select; raise 409 if any reference exists."""
    total = 0
    for stmt in ref_counts:
        total += await session.scalar(stmt) or 0
    if total:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{label} використовується у {total} записах — видалення заборонено",
        )


async def _audit(
    session: AsyncSession,
    action: AuditAction,
    entity_type: str,
    entity_id: int,
    payload: dict[str, Any],
) -> None:
    await audit_append(
        session,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )


# --------------------------------------------------------------------------
# item types
# --------------------------------------------------------------------------

@router.get("/item-types", response_model=list[ItemTypeOut])
async def list_item_types(session: AsyncSession = Depends(get_session)) -> list[ItemType]:
    rows = await session.scalars(select(ItemType).order_by(ItemType.code))
    return list(rows)


@router.post("/item-types", response_model=ItemTypeOut, status_code=201, dependencies=[_admin])
async def create_item_type(
    payload: ItemTypeIn, session: AsyncSession = Depends(get_session)
) -> ItemType:
    await _ensure_unique_code(session, ItemType, payload.code)
    obj = ItemType(**payload.model_dump())
    session.add(obj)
    await session.flush()
    await _audit(session, AuditAction.DICTIONARY_CREATED, "item_type", obj.id,
                 {"code": obj.code, "name_uk": obj.name_uk})
    await session.commit()
    await session.refresh(obj)
    return obj


@router.patch("/item-types/{obj_id}", response_model=ItemTypeOut, dependencies=[_admin])
async def update_item_type(
    obj_id: int, payload: ItemTypeUpdate, session: AsyncSession = Depends(get_session)
) -> ItemType:
    obj = await _get_or_404(session, ItemType, obj_id)
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(obj, k, v)
    await _audit(session, AuditAction.DICTIONARY_UPDATED, "item_type", obj.id,
                 {"code": obj.code, "changed": list(changes)})
    await session.commit()
    await session.refresh(obj)
    return obj


@router.delete("/item-types/{obj_id}", dependencies=[_admin])
async def delete_item_type(
    obj_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    obj = await _get_or_404(session, ItemType, obj_id)
    await _refuse_if_referenced(
        session,
        select(func.count()).select_from(Item).where(Item.item_type_id == obj_id),
        label=f"Тип виробу '{obj.code}'",
    )
    await _audit(session, AuditAction.DICTIONARY_DELETED, "item_type", obj_id,
                 {"code": obj.code})
    await session.delete(obj)
    await session.commit()
    return {"deleted": obj_id}


# --------------------------------------------------------------------------
# operators
# --------------------------------------------------------------------------

@router.get("/operators", response_model=list[OperatorOut])
async def list_operators(session: AsyncSession = Depends(get_session)) -> list[Operator]:
    rows = await session.scalars(select(Operator).order_by(Operator.code))
    return list(rows)


@router.post("/operators", response_model=OperatorOut, status_code=201, dependencies=[_admin])
async def create_operator(
    payload: OperatorIn, session: AsyncSession = Depends(get_session)
) -> Operator:
    await _ensure_unique_code(session, Operator, payload.code)
    obj = Operator(**payload.model_dump())
    session.add(obj)
    await session.flush()
    await _audit(session, AuditAction.DICTIONARY_CREATED, "operator", obj.id,
                 {"code": obj.code, "name_uk": obj.name_uk})
    await session.commit()
    await session.refresh(obj)
    return obj


@router.patch("/operators/{obj_id}", response_model=OperatorOut, dependencies=[_admin])
async def update_operator(
    obj_id: int, payload: OperatorUpdate, session: AsyncSession = Depends(get_session)
) -> Operator:
    obj = await _get_or_404(session, Operator, obj_id)
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(obj, k, v)
    await _audit(session, AuditAction.DICTIONARY_UPDATED, "operator", obj.id,
                 {"code": obj.code, "changed": list(changes)})
    await session.commit()
    await session.refresh(obj)
    return obj


@router.delete("/operators/{obj_id}", dependencies=[_admin])
async def delete_operator(
    obj_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    obj = await _get_or_404(session, Operator, obj_id)
    await _refuse_if_referenced(
        session,
        select(func.count()).select_from(UsageEvent).where(UsageEvent.operator_id == obj_id),
        select(func.count()).select_from(AARCase).where(AARCase.operator_id == obj_id),
        label=f"Експлуатант '{obj.code}'",
    )
    await _audit(session, AuditAction.DICTIONARY_DELETED, "operator", obj_id,
                 {"code": obj.code})
    await session.delete(obj)
    await session.commit()
    return {"deleted": obj_id}


# --------------------------------------------------------------------------
# loss reasons
# --------------------------------------------------------------------------

@router.get("/loss-reasons", response_model=list[ReasonOut])
async def list_loss_reasons(session: AsyncSession = Depends(get_session)) -> list[LossReason]:
    rows = await session.scalars(select(LossReason).order_by(LossReason.code))
    return list(rows)


@router.post("/loss-reasons", response_model=ReasonOut, status_code=201, dependencies=[_admin])
async def create_loss_reason(
    payload: ReasonIn, session: AsyncSession = Depends(get_session)
) -> LossReason:
    await _ensure_unique_code(session, LossReason, payload.code)
    obj = LossReason(**payload.model_dump())
    session.add(obj)
    await session.flush()
    await _audit(session, AuditAction.DICTIONARY_CREATED, "loss_reason", obj.id,
                 {"code": obj.code, "name_uk": obj.name_uk, "zone": obj.zone.value})
    await session.commit()
    await session.refresh(obj)
    return obj


@router.patch("/loss-reasons/{obj_id}", response_model=ReasonOut, dependencies=[_admin])
async def update_loss_reason(
    obj_id: int, payload: ReasonUpdate, session: AsyncSession = Depends(get_session)
) -> LossReason:
    obj = await _get_or_404(session, LossReason, obj_id)
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(obj, k, v)
    await _audit(session, AuditAction.DICTIONARY_UPDATED, "loss_reason", obj.id,
                 {"code": obj.code, "changed": list(changes)})
    await session.commit()
    await session.refresh(obj)
    return obj


@router.delete("/loss-reasons/{obj_id}", dependencies=[_admin])
async def delete_loss_reason(
    obj_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    obj = await _get_or_404(session, LossReason, obj_id)
    await _refuse_if_referenced(
        session,
        select(func.count()).select_from(UsageEvent).where(UsageEvent.loss_reason_id == obj_id),
        label=f"Причина втрат '{obj.code}'",
    )
    await _audit(session, AuditAction.DICTIONARY_DELETED, "loss_reason", obj_id,
                 {"code": obj.code})
    await session.delete(obj)
    await session.commit()
    return {"deleted": obj_id}


# --------------------------------------------------------------------------
# repair reasons
# --------------------------------------------------------------------------

@router.get("/repair-reasons", response_model=list[ReasonOut])
async def list_repair_reasons(
    session: AsyncSession = Depends(get_session),
) -> list[RepairReason]:
    rows = await session.scalars(select(RepairReason).order_by(RepairReason.code))
    return list(rows)


@router.post("/repair-reasons", response_model=ReasonOut, status_code=201, dependencies=[_admin])
async def create_repair_reason(
    payload: ReasonIn, session: AsyncSession = Depends(get_session)
) -> RepairReason:
    await _ensure_unique_code(session, RepairReason, payload.code)
    obj = RepairReason(**payload.model_dump())
    session.add(obj)
    await session.flush()
    await _audit(session, AuditAction.DICTIONARY_CREATED, "repair_reason", obj.id,
                 {"code": obj.code, "name_uk": obj.name_uk, "zone": obj.zone.value})
    await session.commit()
    await session.refresh(obj)
    return obj


@router.patch("/repair-reasons/{obj_id}", response_model=ReasonOut, dependencies=[_admin])
async def update_repair_reason(
    obj_id: int, payload: ReasonUpdate, session: AsyncSession = Depends(get_session)
) -> RepairReason:
    obj = await _get_or_404(session, RepairReason, obj_id)
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(obj, k, v)
    await _audit(session, AuditAction.DICTIONARY_UPDATED, "repair_reason", obj.id,
                 {"code": obj.code, "changed": list(changes)})
    await session.commit()
    await session.refresh(obj)
    return obj


@router.delete("/repair-reasons/{obj_id}", dependencies=[_admin])
async def delete_repair_reason(
    obj_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    obj = await _get_or_404(session, RepairReason, obj_id)
    await _refuse_if_referenced(
        session,
        select(func.count()).select_from(UsageEvent).where(UsageEvent.repair_reason_id == obj_id),
        label=f"Причина ремонту '{obj.code}'",
    )
    await _audit(session, AuditAction.DICTIONARY_DELETED, "repair_reason", obj_id,
                 {"code": obj.code})
    await session.delete(obj)
    await session.commit()
    return {"deleted": obj_id}
