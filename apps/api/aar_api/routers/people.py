"""People directory — the roster from which AAR participants are picked.

Named `/people`, not `/users`, because rows are now *persons* of whom some
can log in (see models/user.py). `/auth/me` and `schemas/auth.MeResponse`
are untouched.

THE PROJECT AXIOM lives in `list_people`: a person's `operator_id` is their
default affiliation and drives SUGGESTIONS ONLY. It appears in ORDER BY,
never in an implicit WHERE — no code path here can hide a person from a
manager. The only narrowing filters are the ones the CALLER asks for.

Modelled line-for-line on routers/dictionaries.py: admin-gated writes,
409 on duplicates, a delete-guard that refuses to orphan references, and an
audit entry on every write.
"""
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.core.rbac import require_role
from aar_api.core.security import hash_password
from aar_api.models.aar import AARCase, IndividualReport
from aar_api.models.audit import AuditAction
from aar_api.models.context import ContextAsset
from aar_api.models.dictionaries import Operator
from aar_api.models.user import ParticipantFunction, Role, User
from aar_api.schemas.people import PersonIn, PersonOut, PersonUpdate, SetPasswordIn
from aar_api.services.audit import append as audit_append

router = APIRouter(prefix="/people", tags=["people"])

_admin = Depends(require_role(Role.ADMIN))
# PII, unlike dictionaries which are open-read.
_reader = Depends(require_role(Role.ADMIN, Role.MANAGER, Role.ANALYST))
# Creating a person is also open to MANAGER (walk-in participant mid-AAR);
# the handler still restricts credential/role minting to ADMIN.
_creator = Depends(require_role(Role.ADMIN, Role.MANAGER))


async def _get_or_404(session: AsyncSession, person_id: int) -> User:
    obj = await session.get(User, person_id)
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
            detail=(
                f"{label} використовується у {total} записах — "
                f"деактивуйте (is_active=false) замість видалення"
            ),
        )


async def _audit(
    session: AsyncSession,
    action: AuditAction,
    entity_id: int,
    payload: dict[str, Any],
) -> None:
    await audit_append(
        session,
        action=action,
        entity_type="person",
        entity_id=entity_id,
        payload=payload,
    )


async def _ensure_email_free(
    session: AsyncSession, email: str, *, exclude_id: int | None = None
) -> None:
    stmt: Select[Any] = select(User.id).where(User.email == email)
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    if await session.scalar(stmt) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"email '{email}' already exists",
        )


async def _ensure_operator_exists(session: AsyncSession, operator_id: int | None) -> None:
    if operator_id is None:
        return
    if await session.get(Operator, operator_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="operator not found"
        )


# --------------------------------------------------------------------------
# read
# --------------------------------------------------------------------------

@router.get("", response_model=list[PersonOut], dependencies=[_reader])
async def list_people(
    operator_id: int | None = Query(default=None),
    function: ParticipantFunction | None = Query(default=None),
    q: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    suggest_for_case_id: int | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[User]:
    """List people; `suggest_for_case_id` only re-orders, never filters.

    People affiliated to the case's operator float to the top of ONE shared
    list; everybody else follows in the same list, in the same response,
    under the same `limit`. When the case has no operator the sort degrades
    to (function, full_name).
    """
    stmt = select(User)
    if operator_id is not None:  # explicit caller-requested filter
        stmt = stmt.where(User.operator_id == operator_id)
    if function is not None:
        stmt = stmt.where(User.function == function)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(User.full_name.ilike(pattern), User.callsign.ilike(pattern))
        )
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))

    case_operator_id: int | None = None
    if suggest_for_case_id is not None:
        case = await session.get(AARCase, suggest_for_case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="case not found")
        case_operator_id = case.operator_id

    if case_operator_id is not None:
        # THE AXIOM: affiliation orders, it never restricts.
        stmt = stmt.order_by(
            sa.case((User.operator_id == case_operator_id, 0), else_=1),
            User.function,
            User.full_name,
        )
    else:
        stmt = stmt.order_by(User.function, User.full_name)

    rows = await session.scalars(stmt.limit(limit))
    return list(rows)


@router.get("/{person_id}", response_model=PersonOut, dependencies=[_reader])
async def get_person(
    person_id: int, session: AsyncSession = Depends(get_session)
) -> User:
    return await _get_or_404(session, person_id)


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------

@router.post("", response_model=PersonOut, status_code=201)
async def create_person(
    payload: PersonIn,
    session: AsyncSession = Depends(get_session),
    claims: dict = _creator,
) -> User:
    """Create a person.

    MANAGER may add a walk-in participant mid-AAR (roster-only), otherwise
    they fall back to free-text names. Only ADMIN may mint credentials or a
    non-participant role.
    """
    is_admin = claims.get("role") == Role.ADMIN.value
    if not is_admin and (payload.password is not None or payload.role != Role.PARTICIPANT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="тільки admin може створювати облікові записи з паролем або роллю",
        )
    if payload.password is not None and payload.email is None:
        # Mirrors ck_users_login_needs_email.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="пароль вимагає email",
        )
    if payload.email is not None:
        await _ensure_email_free(session, payload.email)
    await _ensure_operator_exists(session, payload.operator_id)

    obj = User(
        full_name=payload.full_name,
        callsign=payload.callsign,
        email=payload.email,
        role=payload.role,
        operator_id=payload.operator_id,
        function=payload.function,
        hashed_password=hash_password(payload.password) if payload.password else None,
        is_active=True,
    )
    session.add(obj)
    await session.flush()
    # Field NAMES only — never the name/email. The chain is append-only and
    # nothing written into it can ever be scrubbed.
    await _audit(
        session,
        AuditAction.PERSON_CREATED,
        obj.id,
        {"person_id": obj.id, "fields": sorted(payload.model_dump(exclude_none=True))},
    )
    await session.commit()
    await session.refresh(obj)
    return obj


@router.patch("/{person_id}", response_model=PersonOut, dependencies=[_admin])
async def update_person(
    person_id: int,
    payload: PersonUpdate,
    session: AsyncSession = Depends(get_session),
) -> User:
    obj = await _get_or_404(session, person_id)
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes:
        new_email = changes["email"]
        if new_email is None:
            if obj.hashed_password is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="неможливо прибрати email у користувача з паролем",
                )
        else:
            await _ensure_email_free(session, new_email, exclude_id=person_id)
    if "operator_id" in changes:
        await _ensure_operator_exists(session, changes["operator_id"])
    for k, v in changes.items():
        setattr(obj, k, v)
    await _audit(
        session,
        AuditAction.PERSON_UPDATED,
        obj.id,
        {"person_id": obj.id, "changed": sorted(changes)},
    )
    await session.commit()
    await session.refresh(obj)
    return obj


@router.post("/{person_id}/set-password", response_model=PersonOut, dependencies=[_admin])
async def set_password(
    person_id: int,
    payload: SetPasswordIn,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Roster-only → login promotion.

    One UPDATE on the same row: no id remap, so every historical report FK
    stays valid.
    """
    obj = await _get_or_404(session, person_id)
    if obj.email is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="спершу задайте email"
        )
    obj.hashed_password = hash_password(payload.password)
    await _audit(
        session, AuditAction.PERSON_PASSWORD_SET, obj.id, {"person_id": obj.id}
    )
    await session.commit()
    await session.refresh(obj)
    return obj


@router.delete("/{person_id}", dependencies=[_admin])
async def delete_person(
    person_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    """Delete a person, or refuse when their testimony is on record.

    `individual_reports.user_id` must NEVER become ON DELETE SET NULL:
    nulling it silently converts attributed testimony into a row that reads
    as anonymous, corrupting both ADR-015 semantics and the audit story.
    Deactivate instead.

    Returns a JSON body rather than 204 because the frontend `apiFetch`
    unconditionally parses the response.
    """
    obj = await _get_or_404(session, person_id)
    await _refuse_if_referenced(
        session,
        select(func.count())
        .select_from(IndividualReport)
        .where(IndividualReport.user_id == person_id),
        select(func.count())
        .select_from(IndividualReport)
        .where(IndividualReport.requested_for_user_id == person_id),
        select(func.count())
        .select_from(ContextAsset)
        .where(ContextAsset.validated_by_user_id == person_id),
        label=f"Особа '{obj.full_name}'",
    )
    await _audit(session, AuditAction.PERSON_DELETED, person_id, {"person_id": person_id})
    await session.delete(obj)
    await session.commit()
    return {"deleted": person_id}
