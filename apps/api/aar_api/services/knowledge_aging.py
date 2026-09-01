"""Knowledge decays, and it decays at different speeds (ADR-025).

`ADR-009` lets only `validated` assets feed the mission brief. Nothing ever
expired: an asset validated two years ago was handed to a planner as current
truth. In this domain that is not a stale row, it is the brief asserting
something false — an EW pattern from two years ago describes an adversary that
no longer exists, while a maintenance procedure from the same week may still
hold perfectly.

So freshness is COMPUTED, never a stored state transition:

  * `fresh`  — younger than its half-life; used normally.
  * `aging`  — past the half-life; still used, shown with a caveat.
  * `stale`  — past twice the half-life; still used (a human validated it and
               only a human may retire it — ADR-008 in reverse), but every
               surface must say it needs re-confirmation, and the LLM payload
               marks it so the synthesis cannot assert it as current.

Nothing here auto-deprecates. A machine silently retiring a lesson a person
confirmed is the mirror image of auto-validating one, and we refused that.
The human act is `POST /context/assets/{id}/reaffirm`, which restarts the
clock and is recorded in the audit chain.
"""
from __future__ import annotations

from datetime import UTC, datetime

from aar_api.models.context import ContextAsset, ContextAssetType

#: How long a category of knowledge stays trustworthy without re-confirmation.
#: These are policy defaults, not measurements — a manager overrides any single
#: asset with `review_after_days`. The ordering is the claim being made: what
#: the adversary does changes in weeks, how we build things changes in years.
DEFAULT_HALF_LIFE_DAYS: dict[ContextAssetType, int] = {
    # Adversary behaviour and materiel failure modes — fastest moving.
    ContextAssetType.FAILURE_PATTERN: 90,
    # Crew procedure and drills — a season.
    ContextAssetType.OPERATOR_PRACTICE: 180,
    ContextAssetType.TRAINING_GAP: 180,
    ContextAssetType.EDGE_CASE: 365,
    ContextAssetType.DEPLOYMENT_LESSON: 365,
    ContextAssetType.BUSINESS_RULE: 730,
    ContextAssetType.ACCEPTANCE_CRITERION: 730,
    # A decision about how the thing is built outlives the war it was made in.
    ContextAssetType.ARCHITECTURAL_DECISION: 1825,
}

FRESH = "fresh"
AGING = "aging"
STALE = "stale"


def half_life_days(asset: ContextAsset) -> int:
    """Per-asset override wins over the category default."""
    if asset.review_after_days is not None and asset.review_after_days > 0:
        return asset.review_after_days
    return DEFAULT_HALF_LIFE_DAYS.get(asset.type, 365)


def affirmed_at(asset: ContextAsset) -> datetime | None:
    """When the knowledge was last confirmed by a person.

    Falls back to `validated_at` for rows written before re-affirmation
    existed, and to `created_at` for anything odd, so the age is never
    silently zero — an unknown age must not read as a fresh one.
    """
    return asset.last_affirmed_at or asset.validated_at or asset.created_at


def days_since_affirmed(asset: ContextAsset, now: datetime | None = None) -> int | None:
    ts = affirmed_at(asset)
    if ts is None:
        return None
    now = now or datetime.now(UTC)
    if ts.tzinfo is None:  # SQLite hands back naive datetimes
        ts = ts.replace(tzinfo=UTC)
    return max(0, (now - ts).days)


def freshness(asset: ContextAsset, now: datetime | None = None) -> str:
    """`fresh` / `aging` / `stale` — never a stored column, always derived."""
    age = days_since_affirmed(asset, now)
    if age is None:
        return STALE  # no confirmation on record: treat as needing one
    hl = half_life_days(asset)
    if age < hl:
        return FRESH
    if age < hl * 2:
        return AGING
    return STALE


def asset_out(asset: ContextAsset, now: datetime | None = None) -> dict:
    """Serialisable view of an asset with its freshness attached.

    The three derived fields never live in the database — computing them at the
    boundary is what guarantees no job can retire a lesson behind a human's
    back.
    """
    return {
        **{
            c.name: getattr(asset, c.name)
            for c in asset.__table__.columns
        },
        "freshness": freshness(asset, now),
        "days_since_affirmed": days_since_affirmed(asset, now),
        "half_life_days": half_life_days(asset),
    }
