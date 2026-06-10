from datetime import datetime

from pydantic import BaseModel, ConfigDict

from aar_api.models.aar import CaseStatus, RecommendationStatus, TriggerType


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AARCaseIn(BaseModel):
    title: str
    operator_code: str | None = None
    summary: str | None = None
    what_was_planned: str | None = None
    what_happened: str | None = None
    opr: str | None = None


class AARCasePatch(BaseModel):
    """PATCH /aar/cases/{id} — partial update of NATO fields.

    Status changes go through /transition (which validates the state machine).
    """

    title: str | None = None
    summary: str | None = None
    what_was_planned: str | None = None
    what_happened: str | None = None
    analysis: str | None = None
    lesson_identified: str | None = None
    opr: str | None = None


class CaseTransitionIn(BaseModel):
    """Move a case along the NATO LL state machine."""

    to: CaseStatus
    note: str | None = None
    force: bool = False  # bypass forward-only constraint (admin only)


class AARCaseOut(_Base):
    id: int
    title: str
    status: CaseStatus
    trigger: TriggerType
    operator_id: int | None
    summary: str | None
    what_was_planned: str | None
    what_happened: str | None
    analysis: str | None
    lesson_identified: str | None
    opr: str | None
    analysis_source: str | None
    analysis_drafted_at: datetime | None
    opened_at: datetime
    closed_at: datetime | None


class IndividualReportIn(BaseModel):
    user_id: int
    what_happened: str | None = None
    what_worked: str | None = None
    what_failed: str | None = None
    why: str | None = None
    external_factors: str | None = None
    what_to_change: str | None = None


class IndividualReportOut(_Base):
    id: int
    case_id: int
    user_id: int
    what_happened: str | None
    what_worked: str | None
    what_failed: str | None
    why: str | None
    external_factors: str | None
    what_to_change: str | None
    submitted_at: datetime


class RecommendationIn(BaseModel):
    text: str
    signature: str | None = None  # for auto-validation; e.g. "T2:loss:c"


class RecommendationStatusUpdate(BaseModel):
    status: RecommendationStatus


class RecommendationOut(_Base):
    id: int
    case_id: int
    text: str
    status: RecommendationStatus
    validated_at: datetime | None
    auto_validated_at: datetime | None
    regressed_at: datetime | None
    evidence_count: int
    signature: str | None


class TriggerResult(BaseModel):
    created_case_ids: list[int]
    skipped_existing: int
    auto_validated_recommendation_ids: list[int] = []
    regressed_recommendation_ids: list[int] = []
