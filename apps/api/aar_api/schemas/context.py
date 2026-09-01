from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from aar_api.models.context import AssetStatus, ContextAssetType
from aar_api.models.user import Role


class ContextAssetDraft(BaseModel):
    """What LLM agents return alongside their primary task output."""

    type: ContextAssetType
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    reusable_for: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ContextAssetIn(ContextAssetDraft):
    source: str = Field(min_length=1, max_length=64)
    source_agent: str | None = None
    owner_role: Role = Role.MANAGER


class ContextAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: ContextAssetType
    title: str
    description: str
    source: str
    source_agent: str | None
    status: AssetStatus
    reusable_for: list[str]
    owner_role: Role
    validated_by_user_id: int | None
    validated_at: datetime | None
    superseded_by_id: int | None
    rejection_reason: str | None
    confidence: float | None
    usage_count: int
    created_at: datetime

    # ADR-025 — derived, never stored. See services/knowledge_aging.py.
    last_affirmed_at: datetime | None
    affirmed_count: int
    review_after_days: int | None
    freshness: str
    days_since_affirmed: int | None
    half_life_days: int


class ReviewWindowRequest(BaseModel):
    """Override the category half-life for one asset (null → back to default)."""

    review_after_days: int | None = Field(default=None, ge=1, le=3650)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=512)


class DeprecateRequest(BaseModel):
    superseded_by: int | None = None
