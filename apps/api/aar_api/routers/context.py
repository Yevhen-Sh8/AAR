from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.core.rbac import require_role
from aar_api.models.audit import AuditAction
from aar_api.models.context import AssetStatus, ContextAsset, ContextAssetType
from aar_api.models.user import Role
from aar_api.schemas.context import (
    ContextAssetIn,
    ContextAssetOut,
    DeprecateRequest,
    RejectRequest,
    ReviewWindowRequest,
)
from aar_api.services.audit import append as audit_append
from aar_api.services.context_assets import (
    deprecate_asset,
    reaffirm_asset,
    reject_asset,
    validate_asset,
)
from aar_api.services.knowledge_aging import asset_out

router = APIRouter(prefix="/context", tags=["context"])


async def _get_asset(session: AsyncSession, asset_id: int) -> ContextAsset:
    asset = await session.get(ContextAsset, asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    return asset


@router.get("/assets", response_model=list[ContextAssetOut])
async def list_assets(
    type: ContextAssetType | None = Query(default=None),
    status: AssetStatus | None = Query(default=None),
    source_agent: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[ContextAssetOut]:
    stmt = select(ContextAsset).order_by(ContextAsset.id.desc()).limit(limit)
    if type:
        stmt = stmt.where(ContextAsset.type == type)
    if status:
        stmt = stmt.where(ContextAsset.status == status)
    if source_agent:
        stmt = stmt.where(ContextAsset.source_agent == source_agent)
    rows = await session.scalars(stmt)
    return [ContextAssetOut(**asset_out(a)) for a in rows]


@router.get("/assets/{asset_id}", response_model=ContextAssetOut)
async def get_asset(
    asset_id: int, session: AsyncSession = Depends(get_session)
) -> ContextAssetOut:
    return ContextAssetOut(**asset_out(await _get_asset(session, asset_id)))


@router.post("/assets", response_model=ContextAssetOut, status_code=201)
async def create_asset(
    payload: ContextAssetIn, session: AsyncSession = Depends(get_session)
) -> ContextAssetOut:
    """Manual creation — also starts as DRAFT (ADR-008).

    DELIBERATELY has no `require_role`, unlike validate/reject/deprecate below.
    The asymmetry is the point: a low barrier to *propose* and a high barrier to
    *validate*. A created asset is inert — it starts DRAFT, is never
    auto-validated (ADR-008), and only `validated` assets feed the brief or
    analogy search (ADR-009), so an unprivileged author cannot influence
    anything until a manager/analyst signs it off. Same shape as submitting a
    pre-task signal (ADR-021). Note the production auth-gate still requires a
    valid token here — "open" means any authenticated role, not anonymous.
    """
    asset = ContextAsset(
        type=payload.type,
        title=payload.title,
        description=payload.description,
        source=payload.source,
        source_agent=payload.source_agent or "manual",
        reusable_for=payload.reusable_for,
        confidence=payload.confidence,
        owner_role=payload.owner_role,
        status=AssetStatus.DRAFT,
    )
    session.add(asset)
    await session.flush()
    # persist_drafts() (the LLM path) already writes CONTEXT_ASSET_CREATED;
    # manual creation went unrecorded, so the chain's coverage of asset
    # provenance depended on which path produced it.
    await audit_append(
        session,
        action=AuditAction.CONTEXT_ASSET_CREATED,
        entity_type="context_asset",
        entity_id=asset.id,
        payload={"type": asset.type.value, "title": asset.title, "source": asset.source},
    )
    await session.commit()
    await session.refresh(asset)
    return ContextAssetOut(**asset_out(asset))


@router.post(
    "/assets/{asset_id}/validate",
    response_model=ContextAssetOut,
    dependencies=[Depends(require_role(Role.MANAGER, Role.ANALYST, Role.ADMIN))],
)
async def validate(
    asset_id: int, session: AsyncSession = Depends(get_session)
) -> ContextAssetOut:
    asset = await _get_asset(session, asset_id)
    if asset.status not in (AssetStatus.DRAFT, AssetStatus.REJECTED):
        raise HTTPException(409, f"cannot validate from status={asset.status.value}")
    await validate_asset(session, asset, user_id=None)
    await session.commit()
    await session.refresh(asset)
    return ContextAssetOut(**asset_out(asset))


@router.post(
    "/assets/{asset_id}/reject",
    response_model=ContextAssetOut,
    dependencies=[Depends(require_role(Role.MANAGER, Role.ANALYST, Role.ADMIN))],
)
async def reject(
    asset_id: int,
    payload: RejectRequest,
    session: AsyncSession = Depends(get_session),
) -> ContextAssetOut:
    asset = await _get_asset(session, asset_id)
    if asset.status != AssetStatus.DRAFT:
        raise HTTPException(409, f"can only reject DRAFT, got {asset.status.value}")
    await reject_asset(session, asset, reason=payload.reason)
    await session.commit()
    await session.refresh(asset)
    return ContextAssetOut(**asset_out(asset))


@router.post(
    "/assets/{asset_id}/deprecate",
    response_model=ContextAssetOut,
    dependencies=[Depends(require_role(Role.MANAGER, Role.ADMIN))],
)
async def deprecate(
    asset_id: int,
    payload: DeprecateRequest,
    session: AsyncSession = Depends(get_session),
) -> ContextAssetOut:
    asset = await _get_asset(session, asset_id)
    if asset.status != AssetStatus.VALIDATED:
        raise HTTPException(409, "can only deprecate VALIDATED assets")
    if payload.superseded_by is not None:
        successor = await session.get(ContextAsset, payload.superseded_by)
        if successor is None:
            raise HTTPException(404, "superseded_by asset not found")
    await deprecate_asset(session, asset, superseded_by=payload.superseded_by)
    await session.commit()
    await session.refresh(asset)
    return ContextAssetOut(**asset_out(asset))


@router.post(
    "/assets/{asset_id}/reaffirm",
    response_model=ContextAssetOut,
    dependencies=[Depends(require_role(Role.MANAGER, Role.ANALYST, Role.ADMIN))],
)
async def reaffirm(
    asset_id: int, session: AsyncSession = Depends(get_session)
) -> ContextAssetOut:
    """Confirm an ageing lesson still holds; the freshness clock restarts.

    Only meaningful on a VALIDATED asset: a draft has not been confirmed once
    yet, and a deprecated one was deliberately retired. Re-affirming either
    would launder a status change through the back door.
    """
    asset = await _get_asset(session, asset_id)
    if asset.status != AssetStatus.VALIDATED:
        raise HTTPException(
            409, f"перепідтвердити можна лише validated-актив, а не {asset.status.value}"
        )
    await reaffirm_asset(session, asset, user_id=None)
    await session.commit()
    await session.refresh(asset)
    return ContextAssetOut(**asset_out(asset))


@router.patch(
    "/assets/{asset_id}/review-window",
    response_model=ContextAssetOut,
    dependencies=[Depends(require_role(Role.MANAGER, Role.ADMIN))],
)
async def set_review_window(
    asset_id: int,
    payload: ReviewWindowRequest,
    session: AsyncSession = Depends(get_session),
) -> ContextAssetOut:
    """Override how long THIS asset stays trustworthy; null restores the default.

    The category half-lives are a policy guess. Some lessons are timeless and
    some rot in a fortnight, and the person who wrote it knows better than the
    table does.
    """
    asset = await _get_asset(session, asset_id)
    asset.review_after_days = payload.review_after_days
    await audit_append(
        session,
        action=AuditAction.CONTEXT_ASSET_REAFFIRMED,
        entity_type="context_asset",
        entity_id=asset.id,
        payload={"review_after_days": payload.review_after_days, "window_change": True},
    )
    await session.commit()
    await session.refresh(asset)
    return ContextAssetOut(**asset_out(asset))
