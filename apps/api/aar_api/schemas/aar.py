from datetime import datetime

from pydantic import BaseModel, ConfigDict

from aar_api.models.aar import CaseStatus, RecommendationStatus, TriggerType


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AARCaseIn(BaseModel):
    title: str
    operator_code: str | None = None
    summary: str | None = None


class AARCaseOut(_Base):
    id: int
    title: str
    status: CaseStatus
    trigger: TriggerType
    operator_id: int | None
    summary: str | None
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


class RecommendationStatusUpdate(BaseModel):
    status: RecommendationStatus


class RecommendationOut(_Base):
    id: int
    case_id: int
    text: str
    status: RecommendationStatus
    validated_at: datetime | None


class TriggerResult(BaseModel):
    created_case_ids: list[int]
    skipped_existing: int
