from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from aar_api.models.aar import CaseStatus, RecommendationStatus, TriggerType
from aar_api.models.user import ParticipantFunction


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
    user_id: int | None = None
    anonymous: bool = False
    function: ParticipantFunction | None = None
    what_happened: str | None = None
    what_worked: str | None = None
    what_failed: str | None = None
    why: str | None = None
    external_factors: str | None = None
    what_to_change: str | None = None
    request_id: int | None = None  # fills in an existing stub if provided


class IndividualReportOut(_Base):
    id: int
    case_id: int
    user_id: int | None
    requested_for_user_id: int | None
    anonymous: bool
    function: ParticipantFunction | None = None
    operator_id: int | None = None
    off_roster: bool = False
    what_happened: str | None
    what_worked: str | None
    what_failed: str | None
    why: str | None
    external_factors: str | None
    what_to_change: str | None
    requested_at: datetime | None
    submitted_at: datetime | None


class ParticipantRequestIn(BaseModel):
    """One picked participant, with an optional per-case function override.

    `function` overrides the person's default `users.function` for THIS case
    only; omitting it falls back to the default, and None is a legal outcome
    (rendered as «не вказано», counted in the `"unknown"` coverage bucket).
    """

    user_id: int
    function: ParticipantFunction | None = None


class ReportRequestIn(BaseModel):
    """Manager-side: ask N participants to submit individual reports.

    `user_ids` is DEPRECATED — kept because the pre-Wave-11 frontend and
    tests still send it. It is normalised into `participants` (with
    `function=None`) by the validator below, so the handler only ever deals
    with one shape.
    """

    participants: list[ParticipantRequestIn] | None = None
    user_ids: list[int] | None = None  # DEPRECATED — use `participants`

    @model_validator(mode="after")
    def _normalise(self) -> "ReportRequestIn":
        entries = list(self.participants or [])
        entries += [ParticipantRequestIn(user_id=uid) for uid in (self.user_ids or [])]
        if not entries:
            raise ValueError("потрібно вказати щонайменше одного учасника")
        # Dedupe on user_id, preserving order and the FIRST function given.
        seen: set[int] = set()
        deduped: list[ParticipantRequestIn] = []
        for e in entries:
            if e.user_id in seen:
                continue
            seen.add(e.user_id)
            deduped.append(e)
        self.participants = deduped
        return self

    @property
    def entries(self) -> list[ParticipantRequestIn]:
        """Normalised participant list — always populated post-validation."""
        return self.participants or []


class ReportRequestSummary(BaseModel):
    requested_count: int
    skipped_existing: int
    pending_report_ids: list[int]
    # Wave 11 — advisory only. Nothing here ever blocks anything.
    function_coverage: dict[str, int] = {}
    missing_functions: list[str] = []
    off_roster_user_ids: list[int] = []
    warnings: list[str] = []


class ReportCoverageOut(BaseModel):
    """Advisory read-only view: whose voice is present in this case.

    Never gates a case transition — that would collide with the ADR-010 state
    machine. It exists to make «інакше екіпаж винен за замовчуванням» visible.
    """

    case_id: int
    submitted: int
    pending: int
    functions: dict[str, int]
    zones_covered: list[str]
    zones_missing: list[str]
    off_roster_count: int
    single_function_only: bool
    # Number of participants in the case: with 2 participants, "anonymous" is
    # theatre. Surfaced rather than pretended away.
    anonymity_floor: int


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


# ---------------------------------------------------------------------------
# Participant-facing surface (Wave 12)
#
# The single function the Parallax Debrief concept names as decisive: the
# author of an observation must see what CAME OF IT — not "your report was
# received" but "this procedure changed because of what you wrote". Without
# it their modelling puts submission at 14% instead of 68%, and a Level-2
# system with no testimony is just a metrics dashboard.
# ---------------------------------------------------------------------------

class MyReportRequestOut(BaseModel):
    """A report the current user has been asked for (or has already given)."""

    model_config = ConfigDict(from_attributes=True)
    report_id: int
    case_id: int
    case_title: str
    case_status: CaseStatus
    requested_at: datetime | None
    submitted_at: datetime | None
    anonymous: bool
    function: ParticipantFunction | None = None


class MyObservationRecommendationOut(BaseModel):
    """A concrete change that traces back to the user's testimony."""

    id: int
    text: str
    status: RecommendationStatus
    auto_validated_at: datetime | None = None
    regressed_at: datetime | None = None


class MyObservationOut(BaseModel):
    """What became of one submitted report."""

    report_id: int
    case_id: int
    case_title: str
    case_status: CaseStatus
    submitted_at: datetime | None
    anonymous: bool
    # The outcome, in the author's terms — deliberately a sentence, not a code.
    outcome_uk: str
    lesson_identified: str | None = None
    recommendations: list[MyObservationRecommendationOut] = []
