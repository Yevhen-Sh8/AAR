"""Central dispatcher for outbound notifications on AAR events (Wave 3).

Until now, the only event that fanned out via the integration webhook layer
was `usage_event.created`. This service adds the events that *close the
visibility loop* for the lessons-learned cycle:

    aar_case.created              — new case opened (manual or auto-trigger)
    aar_case.transitioned         — NATO stage change (open→analysed→…)
    aar_case.closed               — case archived
    recommendation.auto_validated — Monitor & Validate stage succeeded
    individual_report.requested   — manager asked N participants to report

Each delivery is signed (HMAC-SHA256) if the subscription has a secret, and
persisted in the `integration_deliveries` table for audit/replay.

Failures are swallowed at this layer — the calling business action must not
be aborted by a partner's downtime. The Delivery row still records the
failure, so an operator can replay later via the existing delivery log UI.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.models.aar import AARCase, IndividualReport, Recommendation
from aar_api.models.integration import WebhookEventKind
from aar_api.services.integrations import canonical_aar_case, dispatch

logger = logging.getLogger(__name__)


def _isoformat(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


async def notify_case_created(session: AsyncSession, case: AARCase) -> None:
    try:
        await dispatch(session, WebhookEventKind.AAR_CASE_CREATED, canonical_aar_case(case))
    except Exception as e:
        logger.exception("notify_case_created failed: %s", e)


async def notify_case_transitioned(
    session: AsyncSession, case: AARCase, from_status: str, note: str | None
) -> None:
    payload: dict[str, Any] = canonical_aar_case(case)
    payload["transition"] = {"from": from_status, "to": case.status.value, "note": note}
    try:
        await dispatch(session, WebhookEventKind.AAR_CASE_TRANSITIONED, payload)
    except Exception as e:
        logger.exception("notify_case_transitioned failed: %s", e)


async def notify_case_closed(session: AsyncSession, case: AARCase) -> None:
    try:
        await dispatch(session, WebhookEventKind.AAR_CASE_CLOSED, canonical_aar_case(case))
    except Exception as e:
        logger.exception("notify_case_closed failed: %s", e)


async def notify_recommendation_auto_validated(
    session: AsyncSession, rec: Recommendation
) -> None:
    payload = {
        "id": rec.id,
        "case_id": rec.case_id,
        "text": rec.text,
        "signature": rec.signature,
        "auto_validated_at": _isoformat(rec.auto_validated_at),
    }
    try:
        await dispatch(
            session, WebhookEventKind.RECOMMENDATION_AUTO_VALIDATED, payload
        )
    except Exception as e:
        logger.exception("notify_recommendation_auto_validated failed: %s", e)


async def notify_report_requested(
    session: AsyncSession, report: IndividualReport
) -> None:
    payload = {
        "id": report.id,
        "case_id": report.case_id,
        "requested_for_user_id": report.requested_for_user_id,
        "requested_at": _isoformat(report.requested_at),
    }
    try:
        await dispatch(
            session, WebhookEventKind.INDIVIDUAL_REPORT_REQUESTED, payload
        )
    except Exception as e:
        logger.exception("notify_report_requested failed: %s", e)
