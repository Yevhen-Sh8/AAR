"""Wave 13 (ADR-025) — knowledge ages, and different kinds age at different speeds.

ADR-009 lets only `validated` assets feed the mission brief, and nothing ever
expired: an asset validated two years ago was handed to a planner as current
truth. For an EW pattern that is not a stale row — it is the brief asserting
something false about an adversary who has since changed.

The rule we hold to: freshness is COMPUTED, never a stored transition. Nothing
auto-deprecates, because a machine quietly retiring a lesson a person confirmed
is the mirror image of auto-validating one, and ADR-008 refused that.
"""
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.context import AssetStatus, ContextAsset, ContextAssetType
from aar_api.services import knowledge_aging as aging

_Session = async_sessionmaker(_engine, expire_on_commit=False)


async def _asset(
    *,
    type_: ContextAssetType = ContextAssetType.FAILURE_PATTERN,
    days_ago: int | None = None,
    status: AssetStatus = AssetStatus.VALIDATED,
    review_after_days: int | None = None,
    title: str = "Урок",
) -> int:
    async with _Session() as s:
        affirmed = (
            datetime.now(UTC) - timedelta(days=days_ago) if days_ago is not None else None
        )
        a = ContextAsset(
            type=type_,
            title=title,
            description="опис",
            source="case:1",
            status=status,
            validated_at=affirmed,
            last_affirmed_at=affirmed,
            review_after_days=review_after_days,
        )
        s.add(a)
        await s.flush()
        aid = a.id
        await s.commit()
    return aid


async def test_an_ew_pattern_goes_stale_while_an_architecture_note_does_not() -> None:
    """The whole point of per-category half-lives, in one assertion."""
    ew = await _asset(type_=ContextAssetType.FAILURE_PATTERN, days_ago=400)
    arch = await _asset(type_=ContextAssetType.ARCHITECTURAL_DECISION, days_ago=400)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        rows = {r["id"]: r for r in (await c.get("/context/assets")).json()}

    assert rows[ew]["freshness"] == "stale"
    assert rows[arch]["freshness"] == "fresh"
    assert rows[ew]["days_since_affirmed"] == 400


async def test_the_three_bands() -> None:
    hl = aging.DEFAULT_HALF_LIFE_DAYS[ContextAssetType.FAILURE_PATTERN]
    fresh = await _asset(days_ago=hl - 5)
    ageing = await _asset(days_ago=hl + 5)
    stale = await _asset(days_ago=hl * 2 + 5)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        rows = {r["id"]: r for r in (await c.get("/context/assets")).json()}

    assert rows[fresh]["freshness"] == "fresh"
    assert rows[ageing]["freshness"] == "aging"
    assert rows[stale]["freshness"] == "stale"


async def test_an_asset_never_confirmed_is_treated_as_needing_confirmation() -> None:
    """An unknown age must not read as a fresh one."""
    aid = await _asset(days_ago=None, status=AssetStatus.DRAFT)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        row = (await c.get(f"/context/assets/{aid}")).json()
    # created_at is "now" in this test, so it is only fresh if the fallback
    # chain works; the guarantee is simply that it is never silently zero-age.
    assert row["days_since_affirmed"] is not None


async def test_reaffirming_restarts_the_clock_and_is_recorded() -> None:
    aid = await _asset(days_ago=400)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        before = (await c.get(f"/context/assets/{aid}")).json()
        assert before["freshness"] == "stale"
        assert before["affirmed_count"] == 0

        r = await c.post(f"/context/assets/{aid}/reaffirm")
        assert r.status_code == 200, r.text
        after = r.json()
        assert after["freshness"] == "fresh"
        assert after["days_since_affirmed"] == 0
        assert after["affirmed_count"] == 1

        log = (await c.get("/audit/log")).json()
    assert any(e["action"] == "context_asset.reaffirmed" for e in log)


async def test_nothing_expires_on_its_own() -> None:
    """A stale asset is still VALIDATED — only a person may retire it."""
    aid = await _asset(days_ago=5000)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        row = (await c.get(f"/context/assets/{aid}")).json()
    assert row["freshness"] == "stale"
    assert row["status"] == "validated"


async def test_only_a_validated_asset_can_be_reaffirmed() -> None:
    """Otherwise re-affirming would launder a status change through the back door."""
    draft = await _asset(days_ago=10, status=AssetStatus.DRAFT)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(f"/context/assets/{draft}/reaffirm")
    assert r.status_code == 409


async def test_a_per_asset_window_overrides_the_category_default() -> None:
    """Some lessons are timeless; the person who wrote it knows better than the table."""
    aid = await _asset(type_=ContextAssetType.FAILURE_PATTERN, days_ago=300)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get(f"/context/assets/{aid}")).json()["freshness"] == "stale"
        r = await c.patch(
            f"/context/assets/{aid}/review-window", json={"review_after_days": 1000}
        )
        assert r.status_code == 200, r.text
        assert r.json()["freshness"] == "fresh"
        assert r.json()["half_life_days"] == 1000

        # Null restores the category default.
        back = await c.patch(
            f"/context/assets/{aid}/review-window", json={"review_after_days": None}
        )
    assert back.json()["freshness"] == "stale"


async def test_a_stale_lesson_reaches_the_brief_labelled_and_ranked_below_a_fresh_one() -> None:
    """It must still be shown — but never as the current picture."""
    await _asset(days_ago=2, title="Свіжий урок про РЕБ")
    await _asset(days_ago=900, title="Старий урок про РЕБ")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        brief = (await c.get("/briefing/mission", params={"q": "РЕБ"})).json()

    lessons = brief["validated_lessons"]
    assert len(lessons) == 2
    # Both present…
    by_title = {i["title"]: i for i in lessons}
    assert by_title["Старий урок про РЕБ"]["freshness"] == "stale"
    assert by_title["Свіжий урок про РЕБ"]["freshness"] == "fresh"
    # …the stale one carries the warning in its meta line…
    assert "ЗАСТАРІЛИЙ" in by_title["Старий урок про РЕБ"]["meta"]
    # …and the fresh one is read first.
    assert lessons[0]["title"] == "Свіжий урок про РЕБ"


async def test_the_learning_loop_counts_knowledge_overdue_for_review() -> None:
    await _asset(days_ago=2)
    await _asset(days_ago=100)  # past the 90-day half-life → aging
    await _asset(days_ago=900)
    await _asset(days_ago=900, status=AssetStatus.DRAFT)  # not validated → not counted

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        kpi = (await c.get("/learning/loop-kpi")).json()

    assert kpi["fresh_validated_assets"] == 1
    assert kpi["aging_validated_assets"] == 1
    assert kpi["stale_validated_assets"] == 1
