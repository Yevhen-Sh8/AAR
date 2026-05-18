"""Persistence and lifecycle of ContextAsset (v1.1).

All transitions write a hash-chained audit entry with a specific
`AuditAction.CONTEXT_ASSET_*` value (ADR-008 — auditability preserved).

Validated-only filter is enforced by `validated_assets()` — `find_analogies`
and other downstream consumers should call this, never raw
`select(ContextAsset)` (ADR-009).
"""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.models.audit import AuditAction
from aar_api.models.context import AssetStatus, AssetUsage, ContextAsset
from aar_api.models.user import Role
from aar_api.schemas.context import ContextAssetDraft
from aar_api.services.audit import append as audit_append


async def persist_drafts(
    session: AsyncSession,
    drafts: list[ContextAssetDraft],
    *,
    source: str,
    source_agent: str,
    owner_role: Role = Role.MANAGER,
) -> list[ContextAsset]:
    """Persist a batch of LLM-produced drafts. Always status=DRAFT (ADR-008)."""
    rows: list[ContextAsset] = []
    for d in drafts:
        rows.append(
            ContextAsset(
                type=d.type,
                title=d.title,
                description=d.description,
                reusable_for=d.reusable_for,
                confidence=d.confidence,
                source=source,
                source_agent=source_agent,
                status=AssetStatus.DRAFT,
                owner_role=owner_role,
            )
        )
    session.add_all(rows)
    await session.flush()
    for asset in rows:
        await audit_append(
            session,
            action=AuditAction.CONTEXT_ASSET_CREATED,
            entity_type="context_asset",
            entity_id=asset.id,
            payload={"type": asset.type.value, "source": source},
        )
    return rows


async def validate_asset(
    session: AsyncSession, asset: ContextAsset, *, user_id: int | None
) -> ContextAsset:
    asset.status = AssetStatus.VALIDATED
    asset.validated_by_user_id = user_id
    asset.validated_at = datetime.now(UTC)
    await audit_append(
        session,
        action=AuditAction.CONTEXT_ASSET_VALIDATED,
        entity_type="context_asset",
        entity_id=asset.id,
        payload={"user_id": user_id},
    )
    return asset


async def reject_asset(
    session: AsyncSession, asset: ContextAsset, *, reason: str
) -> ContextAsset:
    asset.status = AssetStatus.REJECTED
    asset.rejection_reason = reason
    await audit_append(
        session,
        action=AuditAction.CONTEXT_ASSET_REJECTED,
        entity_type="context_asset",
        entity_id=asset.id,
        payload={"reason": reason},
    )
    return asset


async def deprecate_asset(
    session: AsyncSession,
    asset: ContextAsset,
    *,
    superseded_by: int | None,
) -> ContextAsset:
    asset.status = AssetStatus.DEPRECATED
    asset.superseded_by_id = superseded_by
    await audit_append(
        session,
        action=AuditAction.CONTEXT_ASSET_DEPRECATED,
        entity_type="context_asset",
        entity_id=asset.id,
        payload={"superseded_by": superseded_by},
    )
    return asset


async def validated_assets(
    session: AsyncSession, *, limit: int = 50
) -> list[ContextAsset]:
    rows = await session.scalars(
        select(ContextAsset)
        .where(ContextAsset.status == AssetStatus.VALIDATED)
        .order_by(ContextAsset.usage_count.desc(), ContextAsset.id.desc())
        .limit(limit)
    )
    return list(rows)


async def record_usage(
    session: AsyncSession,
    asset: ContextAsset,
    *,
    used_in: str,
    used_by_agent: str | None = None,
) -> None:
    """Increment usage_count for a validated asset surfaced to a task."""
    if asset.status != AssetStatus.VALIDATED:
        return
    asset.usage_count += 1
    session.add(
        AssetUsage(asset_id=asset.id, used_in=used_in, used_by_agent=used_by_agent)
    )
