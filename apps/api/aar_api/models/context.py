"""Context Accumulation Layer (v1.1).

Each AI-assisted task should produce, besides its primary output, structured
context assets that the next task can reuse. See
`docs/concept/v1.1-context-accumulation.md`.

Lifecycle: draft → validated/rejected; validated → used (counter) → deprecated.

Validation is human-gated by policy (ADR-008). Asset becomes searchable in
`find_analogies` only when status == validated (ADR-009).
"""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from aar_api.core.db import Base
from aar_api.models.user import Role


class ContextAssetType(StrEnum):
    BUSINESS_RULE = "business_rule"
    FAILURE_PATTERN = "failure_pattern"
    EDGE_CASE = "edge_case"
    ACCEPTANCE_CRITERION = "acceptance_criterion"
    ARCHITECTURAL_DECISION = "architectural_decision"
    DEPLOYMENT_LESSON = "deployment_lesson"
    OPERATOR_PRACTICE = "operator_practice"
    TRAINING_GAP = "training_gap"


class AssetStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class ContextAsset(Base):
    __tablename__ = "context_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[ContextAssetType] = mapped_column(
        Enum(ContextAssetType, native_enum=False, length=32), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64))                       # "case:42"
    source_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, native_enum=False, length=16),
        default=AssetStatus.DRAFT,
        index=True,
    )
    reusable_for: Mapped[list] = mapped_column(JSON, default=list)
    owner_role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=32), default=Role.MANAGER
    )
    validated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("context_assets.id"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Wave 13 (ADR-025): knowledge ages, and different kinds age at different
    # speeds. `last_affirmed_at` restarts on every human re-confirmation; the
    # freshness itself is computed in services/knowledge_aging.py and never
    # stored, so no background job can quietly retire a validated lesson.
    last_affirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    affirmed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: Overrides the category half-life for this one asset. Null → category default.
    review_after_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    confidence: Mapped[float | None] = mapped_column(nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AssetUsage(Base):
    """Records each time a validated asset was surfaced to a downstream task."""

    __tablename__ = "context_asset_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("context_assets.id"), index=True
    )
    used_in: Mapped[str] = mapped_column(String(64))                       # "case:42"
    used_by_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
