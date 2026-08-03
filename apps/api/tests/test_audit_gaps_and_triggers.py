"""Coverage for branches the audit found untested, plus the fixes it prompted.

Everything here guards behaviour whose regression would be SILENT: a trigger
that stops firing, a tampered chain that still reports ok, a KPI that quietly
counts the wrong cases, or an "immutable" field that was never actually
challenged by its own test.
"""
from datetime import UTC, date, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import AARCase, CaseStatus, TriggerType
from aar_api.models.audit import AuditAction, AuditLog
from aar_api.models.dictionaries import ItemType, LossReason, Operator, Zone
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.services.audit import append as audit_append
from aar_api.services.audit import verify_chain

TODAY = date(2026, 6, 15)
_Session = async_sessionmaker(_engine, expire_on_commit=False)


# ------------------------------------------------------------- T2 trigger

async def _seed_t2() -> str:
    """3 losses with the SAME reason code inside the 7-day window → T2."""
    async with _Session() as s:
        a = ItemType(code="A", name_uk="A")
        op = Operator(code="E-02", name_uk="02")
        lr = LossReason(code="reb", name_uk="РЕБ", zone=Zone.EXTERNAL)
        s.add_all([a, op, lr])
        await s.flush()
        items = [Item(serial_no=f"T2-{i:05d}", item_type_id=a.id) for i in range(3)]
        s.add_all(items)
        await s.flush()
        for i in range(3):
            s.add(
                UsageEvent(
                    item_id=items[i].id,
                    operator_id=op.id,
                    event_date=TODAY - timedelta(days=i),
                    outcome=Outcome.LOST,
                    loss_reason_id=lr.id,
                )
            )
        await s.commit()
    return "reb"


async def test_trigger_t2_repeated_reason_fires_and_is_idempotent() -> None:
    code = await _seed_t2()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/aar/run-triggers", params={"today": TODAY.isoformat()})
        assert r.status_code == 200, r.text
        assert len(r.json()["created_case_ids"]) >= 1

        # Re-running the same day must skip, not duplicate (signature guard).
        again = await client.post(
            "/aar/run-triggers", params={"today": TODAY.isoformat()}
        )
        assert again.json()["skipped_existing"] >= 1

    async with _Session() as s:
        cases = list(
            await s.scalars(
                select(AARCase).where(AARCase.trigger == TriggerType.REPEATED_REASON)
            )
        )
    assert len(cases) == 1, "second run must not create a duplicate case"
    assert f"T2:loss:{code}" in cases[0].title


# ------------------------------------------------------------- T4 trigger

async def _seed_t4() -> None:
    """Enterprise η drops day-over-day by far more than the 10 p.p. threshold."""
    async with _Session() as s:
        a = ItemType(code="A", name_uk="A")
        op = Operator(code="E-04", name_uk="04")
        lr = LossReason(code="x", name_uk="x", zone=Zone.OPERATOR)
        s.add_all([a, op, lr])
        await s.flush()
        items = [Item(serial_no=f"T4-{i:05d}", item_type_id=a.id) for i in range(20)]
        s.add_all(items)
        await s.flush()
        idx = 0
        # Yesterday: 5/5 success (η = 100%)
        for _ in range(5):
            s.add(UsageEvent(item_id=items[idx].id, operator_id=op.id,
                             event_date=TODAY - timedelta(days=1),
                             outcome=Outcome.SUCCESS))
            idx += 1
        # Today: 1/5 success (η = 20%) → a 80 p.p. drop
        s.add(UsageEvent(item_id=items[idx].id, operator_id=op.id,
                         event_date=TODAY, outcome=Outcome.SUCCESS))
        idx += 1
        for _ in range(4):
            s.add(UsageEvent(item_id=items[idx].id, operator_id=op.id,
                             event_date=TODAY, outcome=Outcome.LOST,
                             loss_reason_id=lr.id))
            idx += 1
        await s.commit()


async def test_trigger_t4_enterprise_drop_fires_and_is_idempotent() -> None:
    await _seed_t4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/aar/run-triggers", params={"today": TODAY.isoformat()})
        assert r.status_code == 200, r.text
        again = await client.post(
            "/aar/run-triggers", params={"today": TODAY.isoformat()}
        )
        assert again.json()["skipped_existing"] >= 1

    async with _Session() as s:
        cases = list(
            await s.scalars(
                select(AARCase).where(AARCase.trigger == TriggerType.ENTERPRISE_DROP)
            )
        )
    assert len(cases) == 1, "T4 must fire exactly once for the same day"
    assert f"T4:{TODAY.isoformat()}" in cases[0].title


async def test_auto_opened_cases_reach_the_audit_chain() -> None:
    """Triggers open most cases in production; case-open must be auditable."""
    await _seed_t4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/aar/run-triggers", params={"today": TODAY.isoformat()})

    async with _Session() as s:
        rows = list(
            await s.scalars(
                select(AuditLog).where(AuditLog.action == AuditAction.CASE_CREATED)
            )
        )
    assert rows, "an auto-opened case wrote no CASE_CREATED entry"
    assert any(r.payload.get("auto") is True for r in rows)


# ------------------------------------------------- verify_chain prev_hash

async def test_verify_chain_detects_a_deleted_row() -> None:
    """The prev_hash branch — a DELETED/reordered row, not a tampered one.

    The existing tampering test mutates a payload, which trips the later
    entry_hash check. Removing a row leaves every remaining entry_hash valid
    and can only be caught by the prev_hash linkage.
    """
    async with _Session() as s:
        for i in range(3):
            await audit_append(
                s,
                action=AuditAction.EVENT_CREATED,
                entity_type="usage_event",
                entity_id=i + 1,
                payload={"n": i},
            )
        await s.commit()

    async with _Session() as s:
        status_before = await verify_chain(s)
        assert status_before.ok, status_before.message
        rows = list(await s.scalars(select(AuditLog).order_by(AuditLog.id)))
        assert len(rows) == 3
        await s.delete(rows[1])  # excise the middle link
        await s.commit()

    async with _Session() as s:
        status = await verify_chain(s)
    assert status.ok is False
    assert status.broken_at_id == rows[2].id
    assert "prev_hash mismatch" in status.message


# ------------------------------------------ dictionaries code immutability

async def test_patching_code_does_not_change_it() -> None:
    """The previous assertion never sent `code`, so it proved nothing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = (
            await client.post(
                "/dictionaries/item-types",
                json={"code": "IMM", "name_uk": "Незмінний"},
            )
        ).json()

        upd = await client.patch(
            f"/dictionaries/item-types/{created['id']}",
            json={"code": "HACKED", "name_uk": "Оновлено"},
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["code"] == "IMM", "code must be ignored on PATCH"
        assert upd.json()["name_uk"] == "Оновлено"

        listed = (await client.get("/dictionaries/item-types")).json()
        assert {r["code"] for r in listed} >= {"IMM"}
        assert all(r["code"] != "HACKED" for r in listed)


# ------------------------------------------------- close_case / KPI window

async def test_close_shortcut_stamps_validated_at() -> None:
    """Without the stamp these cases vanish from time-to-validation."""
    async with _Session() as s:
        case = AARCase(title="Закриття навпростець", trigger=TriggerType.MANUAL)
        s.add(case)
        await s.flush()
        case_id = case.id
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(f"/aar/cases/{case_id}/close")
        assert r.status_code == 200, r.text

    async with _Session() as s:
        closed = await s.get(AARCase, case_id)
    assert closed is not None
    assert closed.status == CaseStatus.CLOSED
    assert closed.validated_at is not None, "legacy close must still stamp validated_at"


async def test_loop_kpi_respects_the_upper_bound_of_the_window() -> None:
    """period_to was ignored for cases, so later cases leaked into the window."""
    from aar_api.services.learning_metrics import compute_loop_kpi

    async with _Session() as s:
        # Both are validated, so both would land in the time-to-validation
        # cohort — the only thing that may exclude the later one is period_to.
        inside = AARCase(
            title="У вікні",
            trigger=TriggerType.MANUAL,
            opened_at=datetime(2026, 1, 10, tzinfo=UTC),
            validated_at=datetime(2026, 1, 20, tzinfo=UTC),
        )
        after = AARCase(
            title="Після вікна",
            trigger=TriggerType.MANUAL,
            opened_at=datetime(2026, 5, 10, tzinfo=UTC),
            validated_at=datetime(2026, 5, 20, tzinfo=UTC),
        )
        s.add_all([inside, after])
        await s.commit()

    async with _Session() as s:
        kpi = await compute_loop_kpi(
            s,
            period_from=datetime(2026, 1, 1, tzinfo=UTC),
            period_to=datetime(2026, 2, 1, tzinfo=UTC),
        )

    # Exactly the one case opened inside the window is counted.
    assert kpi.cases_with_validation == 1, (
        "case opened after period_to leaked into the window: "
        f"{kpi.cases_with_validation}"
    )
