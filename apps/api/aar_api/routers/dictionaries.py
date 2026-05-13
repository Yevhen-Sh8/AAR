from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason
from aar_api.schemas.dictionaries import ItemTypeOut, OperatorOut, ReasonOut

router = APIRouter(prefix="/dictionaries", tags=["dictionaries"])


@router.get("/item-types", response_model=list[ItemTypeOut])
async def list_item_types(session: AsyncSession = Depends(get_session)) -> list[ItemType]:
    rows = await session.scalars(select(ItemType).order_by(ItemType.code))
    return list(rows)


@router.get("/operators", response_model=list[OperatorOut])
async def list_operators(session: AsyncSession = Depends(get_session)) -> list[Operator]:
    rows = await session.scalars(select(Operator).order_by(Operator.code))
    return list(rows)


@router.get("/loss-reasons", response_model=list[ReasonOut])
async def list_loss_reasons(session: AsyncSession = Depends(get_session)) -> list[LossReason]:
    rows = await session.scalars(select(LossReason).order_by(LossReason.code))
    return list(rows)


@router.get("/repair-reasons", response_model=list[ReasonOut])
async def list_repair_reasons(
    session: AsyncSession = Depends(get_session),
) -> list[RepairReason]:
    rows = await session.scalars(select(RepairReason).order_by(RepairReason.code))
    return list(rows)
