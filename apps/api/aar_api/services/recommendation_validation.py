"""Monitor & Validate stage of the NATO LL cycle.

Closes the loop literature calls failure mode #1: lessons observed but never
validated. After a recommendation is marked DONE, this service watches for
recurrence of the signature pattern over a validation window:

  - no recurrence  → auto_validated_at set, status → VALIDATED
                     (the Lesson is now truly Learned)
  - recurrence     → regressed_at set, status → IN_PROGRESS
                     (and evidence_count += 1)

`signature` is the same string family used by the trigger engine
(e.g. "T2:loss:c" or "T1:Е-07"), so we can ask: "did the same problem fire
again?"

Run from `evaluate_triggers()` once per day.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.models.aar import Recommendation, RecommendationStatus
from aar_api.models.audit import AuditAction
from aar_api.services.audit import append as audit_append
from aar_api.services.notifications import notify_recommendation_auto_validated


@dataclass(frozen=True)
class ValidationConfig:
    """Window during which a DONE recommendation must remain clean to be
    auto-validated. Default 14 days aligns with T2's 7-day window × 2."""

    quiet_window_days: int = 14


async def auto_validate_recommendations(
    session: AsyncSession,
    today: date,
    recurring_signatures: set[str],
    cfg: ValidationConfig | None = None,
) -> tuple[list[int], list[int]]:
    """Walk DONE recommendations and decide auto-validate or regress.

    Args:
        recurring_signatures: signatures that fired today (from trigger engine).
            E.g. {"T2:loss:c:2026-06-10", "T1:Е-07:2026-06-10"}.
            The date suffix is stripped before comparison.

    Returns: (auto_validated_ids, regressed_ids)
    """
    cfg = cfg or ValidationConfig()
    now = datetime.now(UTC)
    cutoff = today - timedelta(days=cfg.quiet_window_days)

    # Strip date suffix from signatures fired today.
    todays_patterns = {_pattern(sig) for sig in recurring_signatures}

    # Index: today's recurrences increment evidence_count on matching DONE recs.
    by_pattern: dict[str, list[Recommendation]] = defaultdict(list)
    done_recs = list(
        await session.scalars(
            select(Recommendation).where(
                Recommendation.status == RecommendationStatus.DONE,
                Recommendation.signature.is_not(None),
            )
        )
    )
    for rec in done_recs:
        if rec.signature:
            by_pattern[_pattern(rec.signature)].append(rec)

    auto_validated: list[int] = []
    regressed: list[int] = []

    # Phase 1: regressions — signature fired again today.
    for pattern in todays_patterns:
        for rec in by_pattern.get(pattern, []):
            rec.status = RecommendationStatus.IN_PROGRESS
            rec.regressed_at = now
            rec.evidence_count += 1
            await audit_append(
                session,
                action=AuditAction.RECOMMENDATION_REGRESSED,
                entity_type="recommendation",
                entity_id=rec.id,
                payload={
                    "signature": rec.signature,
                    "evidence_count": rec.evidence_count,
                    "reason": "trigger_recurrence",
                },
            )
            regressed.append(rec.id)

    # Phase 2: validations — DONE long enough without recurrence.
    # Use validated_at as proxy for "marked DONE at" — services that flip status
    # to DONE should stamp validated_at if no later step does so. (Backstop:
    # treat NULL validated_at as eligible since the rec exists.)
    regressed_ids = set(regressed)
    for rec in done_recs:
        if rec.id in regressed_ids:
            continue
        # If recommendation has been DONE since before the cutoff and we saw
        # no recurrence today, count it validated.
        eligible_since = rec.validated_at or rec.regressed_at
        if eligible_since is None or eligible_since.date() <= cutoff:
            rec.status = RecommendationStatus.VALIDATED
            rec.auto_validated_at = now
            await audit_append(
                session,
                action=AuditAction.RECOMMENDATION_AUTO_VALIDATED,
                entity_type="recommendation",
                entity_id=rec.id,
                payload={
                    "signature": rec.signature,
                    "quiet_days": cfg.quiet_window_days,
                },
            )
            await notify_recommendation_auto_validated(session, rec)
            auto_validated.append(rec.id)

    return auto_validated, regressed


def _pattern(signature: str) -> str:
    """Strip trailing :YYYY-MM-DD if present."""
    parts = signature.rsplit(":", 1)
    if len(parts) == 2 and len(parts[1]) == 10 and parts[1][4] == "-":
        return parts[0]
    return signature
