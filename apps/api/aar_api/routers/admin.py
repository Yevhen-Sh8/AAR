"""Wave 5 hardening: browser-only data export for pilot backup hygiene.

Render's free Postgres plan has no automatic backups and expires after 90
days (see docs/DEPLOY.md). This deploy is operated entirely from a browser
(no terminal/shell access), so a full pg_dump workflow isn't practical day
to day. This endpoint lets an admin download a complete JSON snapshot of the
operational tables straight from the browser as a supplementary safety net.

This is NOT a substitute for real point-in-time recovery — for production
use, upgrade the Render Postgres plan (adds automated daily backups + PITR)
per docs/DEPLOY.md.
"""
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api import __version__
from aar_api.core.db import get_session
from aar_api.core.rbac import require_role
from aar_api.models.aar import AARCase, IndividualReport, Recommendation
from aar_api.models.context import ContextAsset
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason
from aar_api.models.event import Item, UsageEvent
from aar_api.models.user import Role, User

router = APIRouter(prefix="/admin", tags=["admin"])

_EXPORTED_TABLES: list[tuple[str, Any, frozenset[str]]] = [
    ("item_types", ItemType, frozenset()),
    ("operators", Operator, frozenset()),
    ("loss_reasons", LossReason, frozenset()),
    ("repair_reasons", RepairReason, frozenset()),
    ("items", Item, frozenset()),
    ("usage_events", UsageEvent, frozenset()),
    ("aar_cases", AARCase, frozenset()),
    ("individual_reports", IndividualReport, frozenset()),
    ("recommendations", Recommendation, frozenset()),
    ("context_assets", ContextAsset, frozenset()),
    ("users", User, frozenset({"hashed_password"})),  # never export credentials
]


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _row_to_dict(row: Any, exclude: frozenset[str]) -> dict[str, Any]:
    return {
        col.name: _json_safe(getattr(row, col.name))
        for col in row.__table__.columns
        if col.name not in exclude
    }


@router.get("/export", dependencies=[Depends(require_role(Role.ADMIN))])
async def export_backup(session: AsyncSession = Depends(get_session)) -> Response:
    """Full JSON snapshot of operational tables, admin-only. Downloadable."""
    tables: dict[str, list[dict[str, Any]]] = {}
    for name, model, exclude in _EXPORTED_TABLES:
        rows = list(await session.scalars(select(model)))
        tables[name] = [_row_to_dict(r, exclude) for r in rows]

    now = datetime.now(UTC)
    payload = {
        "exported_at": now.isoformat(),
        "app_version": __version__,
        "tables": tables,
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"aar-backup-{now.strftime('%Y%m%d-%H%M%S')}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
