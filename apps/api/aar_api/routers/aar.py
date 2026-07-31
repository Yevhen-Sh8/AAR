from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.core.rbac import has_role, optional_claims, require_role
from aar_api.models.aar import (
    ALLOWED_TRANSITIONS,
    EXPECTED_FUNCTIONS,
    FUNCTION_ZONE_AFFINITY,
    AARCase,
    CaseStatus,
    IndividualReport,
    Recommendation,
    RecommendationStatus,
    TriggerType,
)
from aar_api.models.audit import AuditAction
from aar_api.models.dictionaries import Operator, Zone
from aar_api.models.user import ParticipantFunction, Role, User
from aar_api.schemas.aar import (
    AARCaseIn,
    AARCaseOut,
    AARCasePatch,
    CaseTransitionIn,
    IndividualReportIn,
    IndividualReportOut,
    RecommendationIn,
    RecommendationOut,
    RecommendationStatusUpdate,
    ReportCoverageOut,
    ReportRequestIn,
    ReportRequestSummary,
    TriggerResult,
)
from aar_api.services import redaction
from aar_api.services.audit import append as audit_append
from aar_api.services.notifications import (
    notify_case_closed,
    notify_case_created,
    notify_case_transitioned,
    notify_report_requested,
)
from aar_api.services.triggers import TriggerConfig, evaluate_triggers

router = APIRouter(prefix="/aar", tags=["aar"])

# Participants must not read each other's testimony.
_report_reader = Depends(require_role(Role.ADMIN, Role.MANAGER, Role.ANALYST))


async def _get_case(session: AsyncSession, case_id: int) -> AARCase:
    case = await session.get(AARCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@router.post("/cases", response_model=AARCaseOut, status_code=201)
async def create_case(
    payload: AARCaseIn, session: AsyncSession = Depends(get_session)
) -> AARCase:
    op_id: int | None = None
    if payload.operator_code:
        op = await session.scalar(select(Operator).where(Operator.code == payload.operator_code))
        if op is None:
            raise HTTPException(404, f"operator '{payload.operator_code}' not found")
        op_id = op.id
    case = AARCase(
        title=payload.title,
        operator_id=op_id,
        summary=payload.summary,
        what_was_planned=payload.what_was_planned,
        what_happened=payload.what_happened,
        opr=payload.opr,
        trigger=TriggerType.MANUAL,
    )
    session.add(case)
    await session.flush()
    await audit_append(
        session,
        action=AuditAction.CASE_CREATED,
        entity_type="aar_case",
        entity_id=case.id,
        payload={"title": case.title, "trigger": case.trigger.value},
    )
    await notify_case_created(session, case)
    await session.commit()
    await session.refresh(case)
    return case


@router.get("/cases", response_model=list[AARCaseOut])
async def list_cases(
    status: CaseStatus | None = Query(default=None),
    trigger: TriggerType | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[AARCase]:
    stmt = select(AARCase).order_by(AARCase.opened_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(AARCase.status == status)
    if trigger:
        stmt = stmt.where(AARCase.trigger == trigger)
    return list(await session.scalars(stmt))


@router.get("/cases/{case_id}", response_model=AARCaseOut)
async def get_case(case_id: int, session: AsyncSession = Depends(get_session)) -> AARCase:
    return await _get_case(session, case_id)


@router.patch("/cases/{case_id}", response_model=AARCaseOut)
async def patch_case(
    case_id: int,
    payload: AARCasePatch,
    session: AsyncSession = Depends(get_session),
) -> AARCase:
    """Edit NATO LL narrative fields (analysis, lesson_identified, etc.).

    Status changes must go through /transition.
    """
    case = await _get_case(session, case_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(case, k, v)
    if "analysis" in data and data["analysis"]:
        case.analysis_source = case.analysis_source or "manual"
        case.analysis_drafted_at = case.analysis_drafted_at or datetime.now(UTC)
        await audit_append(
            session,
            action=AuditAction.CASE_ANALYSIS_DRAFTED,
            entity_type="aar_case",
            entity_id=case.id,
            payload={"source": case.analysis_source, "via": "patch"},
        )
    await session.commit()
    await session.refresh(case)
    return case


@router.post("/cases/{case_id}/transition", response_model=AARCaseOut)
async def transition_case(
    case_id: int,
    payload: CaseTransitionIn,
    session: AsyncSession = Depends(get_session),
) -> AARCase:
    """Move case along the NATO LL state machine.

    Forward-only by default; `force=True` allows admin overrides (used by
    automated regression).
    """
    case = await _get_case(session, case_id)
    target = payload.to
    if not payload.force:
        allowed = ALLOWED_TRANSITIONS.get(case.status, set())
        if target not in allowed:
            raise HTTPException(
                409,
                f"transition {case.status.value} → {target.value} not allowed "
                f"(allowed: {sorted(s.value for s in allowed)})",
            )
    prev = case.status
    case.status = target
    now = datetime.now(UTC)
    if target == CaseStatus.VALIDATED and case.validated_at is None:
        case.validated_at = now
    if target == CaseStatus.CLOSED:
        case.closed_at = now
        # If validated_at wasn't stamped (legacy flow), stamp it now so KPIs
        # still get a sane value.
        if case.validated_at is None:
            case.validated_at = now
    await audit_append(
        session,
        action=AuditAction.CASE_TRANSITIONED,
        entity_type="aar_case",
        entity_id=case.id,
        payload={"from": prev.value, "to": target.value, "note": payload.note},
    )
    await notify_case_transitioned(session, case, prev.value, payload.note)
    if target == CaseStatus.CLOSED:
        await notify_case_closed(session, case)
    await session.commit()
    await session.refresh(case)
    return case


@router.post("/cases/{case_id}/close", response_model=AARCaseOut)
async def close_case(case_id: int, session: AsyncSession = Depends(get_session)) -> AARCase:
    """Legacy shortcut: jump directly to CLOSED. Prefer /transition for
    proper NATO-cycle tracking."""
    case = await _get_case(session, case_id)
    case.status = CaseStatus.CLOSED
    now = datetime.now(UTC)
    case.closed_at = now
    # Mirror /transition: without this stamp a case closed via the legacy
    # shortcut has validated_at NULL forever, and learning_metrics silently
    # drops it from time-to-validation — the shortcut quietly shrank the
    # very KPI that measures whether the loop works.
    if case.validated_at is None:
        case.validated_at = now
    await audit_append(
        session,
        action=AuditAction.CASE_CLOSED,
        entity_type="aar_case",
        entity_id=case.id,
        payload={"title": case.title},
    )
    await notify_case_closed(session, case)
    await session.commit()
    await session.refresh(case)
    return case


@router.post(
    "/cases/{case_id}/reports", response_model=IndividualReportOut, status_code=201
)
async def add_report(
    case_id: int,
    payload: IndividualReportIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(optional_claims),
) -> IndividualReportOut:
    """Submit an individual AAR report.

    Open to any authenticated caller — participants submit through it.

    If `request_id` points to an existing pending request stub, that row is
    filled in (preserving `requested_at` and the function/operator snapshot).
    Otherwise a new row is created.

    `anonymous=True` nulls `user_id` on the row AND makes the serialization
    layer hide `requested_for_user_id` / `operator_id` (and `function` when
    the person is its sole holder in the case) from non-admins. The audit
    chain records the originator either way — see services/redaction.py.
    """
    await _get_case(session, case_id)
    now = datetime.now(UTC)
    data = payload.model_dump(exclude={"request_id"})

    # The originator recorded in the chain must be a real person.
    if payload.user_id is not None:
        if await session.get(User, payload.user_id) is None:
            raise HTTPException(404, f"user not found: {payload.user_id}")

    if payload.request_id is not None:
        stub = await session.get(IndividualReport, payload.request_id)
        if stub is None or stub.case_id != case_id:
            raise HTTPException(404, "report request not found for this case")
        if stub.submitted_at is not None:
            raise HTTPException(409, "report already submitted")
        # Impersonation hardening: without this, any caller could fill
        # someone else's stub under a third person's id, making the audit
        # originator, the function snapshot and off_roster all lie.
        if payload.user_id is not None and payload.user_id != stub.requested_for_user_id:
            raise HTTPException(409, "user_id не відповідає адресату запиту")
        originator = payload.user_id or stub.requested_for_user_id
        snapshot_function = stub.function
        for k, v in data.items():
            if k == "function" and v is None:
                continue  # keep the snapshot taken at request time
            setattr(stub, k, v)
        if payload.function is not None:
            snapshot_function = payload.function
        stub.submitted_at = now
        if payload.anonymous:
            stub.user_id = None
        await session.flush()
        await _audit_report_submitted(
            session,
            row=stub,
            case_id=case_id,
            request_id=payload.request_id,
            anonymous=payload.anonymous,
            originator_user_id=originator,
            function=snapshot_function,
        )
        await session.commit()
        await session.refresh(stub)
        return redaction.report_out(stub, reveal=has_role(claims, Role.ADMIN))

    report = IndividualReport(case_id=case_id, submitted_at=now, **data)
    if payload.anonymous:
        report.user_id = None
    session.add(report)
    await session.flush()  # assign the id before the audit entry references it
    await _audit_report_submitted(
        session,
        row=report,
        case_id=case_id,
        request_id=None,
        anonymous=payload.anonymous,
        originator_user_id=payload.user_id,
        function=payload.function,
    )
    await session.commit()
    await session.refresh(report)
    return redaction.report_out(report, reveal=has_role(claims, Role.ADMIN))


async def _audit_report_submitted(
    session: AsyncSession,
    *,
    row: IndividualReport,
    case_id: int,
    request_id: int | None,
    anonymous: bool,
    originator_user_id: int | None,
    function: ParticipantFunction | None,
) -> None:
    """BUG-2 fix: creating/filling a report is state-changing — record it.

    The payload is built PRE-redaction from the request, so the chain holds
    the true originator even for an anonymous submission (whose row has
    `user_id` nulled). `GET /audit/log` redacts it again for non-admins via
    services/redaction.audit_payload — the stored bytes, and therefore the
    hash chain, are untouched.

    `actor` stays None, consistent with routers/dictionaries.py: the
    originator lives in the payload, which is what gets redacted.
    """
    await audit_append(
        session,
        action=AuditAction.INDIVIDUAL_REPORT_SUBMITTED,
        entity_type="individual_report",
        entity_id=row.id,
        payload={
            "case_id": case_id,
            "request_id": request_id,
            "anonymous": anonymous,
            "originator_user_id": originator_user_id,
            "function": function.value if function else None,
            "off_roster": row.off_roster,
        },
    )


@router.post(
    "/cases/{case_id}/request-reports",
    response_model=ReportRequestSummary,
    status_code=201,
    dependencies=[_report_reader],
)
async def request_reports(
    case_id: int,
    payload: ReportRequestIn,
    session: AsyncSession = Depends(get_session),
) -> ReportRequestSummary:
    """Manager-side workflow: ask N participants to submit individual reports.

    Creates one pending IndividualReport stub per picked person (skipping
    people who already have an unsubmitted request for this case) and
    dispatches `individual_report.requested` so downstream messengers can
    notify them.

    THE AXIOM: a person's affiliation never restricts the pick. Choosing
    someone from another operator returns 201 and records the divergence as
    the FACT `off_roster=true` plus an audit entry plus an advisory string in
    `warnings[]` — never a 403/409. The single blocking condition on a person
    is `is_active=false`, which is about employment, not affiliation.
    """
    case = await _get_case(session, case_id)
    now = datetime.now(UTC)
    entries = payload.entries
    ids = [e.user_id for e in entries]

    # Resolve the ids for real. Before Wave 11 any int was accepted, so a
    # stub could be created with a dangling FK value — invisible on SQLite
    # (tests never enable PRAGMA foreign_keys) and a 500 on Postgres.
    users = {
        u.id: u for u in await session.scalars(select(User).where(User.id.in_(ids)))
    }
    missing = set(ids) - set(users)
    if missing:
        raise HTTPException(404, f"users not found: {sorted(missing)}")
    inactive = sorted(uid for uid in ids if not users[uid].is_active)
    if inactive:
        raise HTTPException(409, f"неактивні особи: {inactive}")

    existing_rows = list(
        await session.scalars(
            select(IndividualReport).where(
                IndividualReport.case_id == case_id,
                IndividualReport.requested_for_user_id.in_(ids),
                IndividualReport.submitted_at.is_(None),
            )
        )
    )
    existing_for = {r.requested_for_user_id for r in existing_rows}

    created: list[IndividualReport] = []
    skipped = 0
    off_roster_ids: list[int] = []
    warnings: list[str] = []
    for entry in entries:
        if entry.user_id in existing_for:
            skipped += 1
            continue
        user = users[entry.user_id]
        eff_function = entry.function or user.function
        # NO OPERATOR FILTER — recorded, not blocked.
        off_roster = case.operator_id is not None and user.operator_id != case.operator_id
        if off_roster:
            off_roster_ids.append(entry.user_id)
            warnings.append(
                f"{user.full_name} — поза складом експлуатанта цього кейсу "
                f"(це не помилка: свідчення ззовні підвищує якість атрибуції)"
            )
        stub = IndividualReport(
            case_id=case_id,
            requested_for_user_id=entry.user_id,
            requested_at=now,
            function=eff_function,
            operator_id=user.operator_id,
            off_roster=off_roster,
        )
        session.add(stub)
        created.append(stub)
    await session.flush()
    for stub in created:
        await audit_append(
            session,
            action=AuditAction.INDIVIDUAL_REPORT_REQUESTED,
            entity_type="individual_report",
            entity_id=stub.id,
            payload={
                "case_id": case_id,
                "requested_for_user_id": stub.requested_for_user_id,
                "function": stub.function.value if stub.function else None,
                "off_roster": stub.off_roster,
            },
        )
        await notify_report_requested(session, stub)
    await session.commit()

    coverage = await _function_coverage(session, case_id)
    return ReportRequestSummary(
        requested_count=len(created),
        skipped_existing=skipped,
        pending_report_ids=[r.id for r in created],
        function_coverage=coverage,
        missing_functions=[
            f.value for f in EXPECTED_FUNCTIONS if not coverage.get(f.value)
        ],
        off_roster_user_ids=off_roster_ids,
        warnings=warnings,
    )


async def _function_coverage(session: AsyncSession, case_id: int) -> dict[str, int]:
    """GROUP BY over the single-table snapshot. NULL lands in "unknown"."""
    rows = await session.execute(
        select(IndividualReport.function, func.count())
        .where(IndividualReport.case_id == case_id)
        .group_by(IndividualReport.function)
    )
    coverage: dict[str, int] = {}
    for fn, count in rows.all():
        key = fn.value if isinstance(fn, ParticipantFunction) else (fn or "unknown")
        coverage[key] = coverage.get(key, 0) + count
    return coverage


@router.get(
    "/cases/{case_id}/reports",
    response_model=list[IndividualReportOut],
    dependencies=[_report_reader],
)
async def list_reports(
    case_id: int,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(optional_claims),
) -> list[IndividualReportOut]:
    await _get_case(session, case_id)
    rows = list(
        await session.scalars(
            select(IndividualReport).where(IndividualReport.case_id == case_id)
        )
    )
    reveal = has_role(claims, Role.ADMIN)
    counts = redaction.function_counts(rows)
    return [
        redaction.report_out(r, reveal=reveal, case_function_counts=counts)
        for r in rows
    ]


@router.get(
    "/report-coverage",
    response_model=ReportCoverageOut,
    dependencies=[_report_reader],
)
async def report_coverage(
    case_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
) -> ReportCoverageOut:
    """Whose voice is present in this case — advisory, never a gate.

    Flat path on purpose: the frontend demo-mode router matches mock routes
    by `startsWith`, and the existing "/aar/cases" key already swallows
    "/aar/cases/{id}/…", so a nested path would be unmockable.

    Nothing here is stored (ADR-013): it is a GROUP BY over the report
    snapshots plus FUNCTION_ZONE_AFFINITY.
    """
    await _get_case(session, case_id)
    rows = list(
        await session.scalars(
            select(IndividualReport).where(IndividualReport.case_id == case_id)
        )
    )
    functions: dict[str, int] = {}
    for r in rows:
        key = r.function.value if r.function else "unknown"
        functions[key] = functions.get(key, 0) + 1

    # Zone.UNKNOWN is not an attributable zone — it is the "we don't know"
    # bucket, so it is neither claimed as covered nor reported as missing.
    covered_zones = {
        FUNCTION_ZONE_AFFINITY[f].value
        for f in ParticipantFunction
        if functions.get(f.value) and FUNCTION_ZONE_AFFINITY[f] is not Zone.UNKNOWN
    }
    all_zones = {
        z.value for z in FUNCTION_ZONE_AFFINITY.values() if z is not Zone.UNKNOWN
    }
    known = [k for k in functions if k != "unknown"]
    return ReportCoverageOut(
        case_id=case_id,
        submitted=sum(1 for r in rows if r.submitted_at is not None),
        pending=sum(1 for r in rows if r.submitted_at is None),
        functions=functions,
        zones_covered=sorted(covered_zones),
        zones_missing=sorted(all_zones - covered_zones),
        off_roster_count=sum(1 for r in rows if r.off_roster),
        # «свідчення лише від однієї функції — атрибуція зони втрати ненадійна»
        single_function_only=len(known) == 1,
        anonymity_floor=len(rows),
    )


@router.post(
    "/cases/{case_id}/recommendations",
    response_model=RecommendationOut,
    status_code=201,
)
async def add_recommendation(
    case_id: int,
    payload: RecommendationIn,
    session: AsyncSession = Depends(get_session),
) -> Recommendation:
    case = await _get_case(session, case_id)
    sig = payload.signature
    if sig is None and case.title and "[" in case.title:
        # Extract auto-trigger signature from the case title pattern "[T#:key:date]"
        import re

        m = re.search(r"\[(T\d:[^\]]+)\]", case.title)
        if m:
            sig = m.group(1)
    rec = Recommendation(case_id=case_id, text=payload.text, signature=sig)
    session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec


@router.patch(
    "/recommendations/{rec_id}",
    response_model=RecommendationOut,
)
async def update_recommendation_status(
    rec_id: int,
    payload: RecommendationStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> Recommendation:
    rec = await session.get(Recommendation, rec_id)
    if rec is None:
        raise HTTPException(404, "recommendation not found")
    rec.status = payload.status
    if payload.status == RecommendationStatus.VALIDATED:
        rec.validated_at = datetime.now(UTC)
    elif payload.status == RecommendationStatus.DONE:
        # Stamp validated_at as the "DONE since" marker for auto-validation.
        rec.validated_at = datetime.now(UTC)
    await audit_append(
        session,
        action=AuditAction.RECOMMENDATION_UPDATED,
        entity_type="recommendation",
        entity_id=rec.id,
        payload={"status": rec.status.value},
    )
    await session.commit()
    await session.refresh(rec)
    return rec


@router.post("/run-triggers", response_model=TriggerResult)
async def run_triggers(
    today: date = Query(default_factory=lambda: datetime.now(UTC).date()),
    session: AsyncSession = Depends(get_session),
) -> TriggerResult:
    created, skipped, auto_validated, regressed = await evaluate_triggers(
        session, today, TriggerConfig()
    )
    await session.commit()
    return TriggerResult(
        created_case_ids=[c.id for c in created],
        skipped_existing=skipped,
        auto_validated_recommendation_ids=auto_validated,
        regressed_recommendation_ids=regressed,
    )
