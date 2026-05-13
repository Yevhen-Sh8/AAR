"""Seed synthetic data for November–December for local development and tests.

Usage:
    python -m aar_api.scripts.seed
"""
import asyncio
import random
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from aar_api.core.config import get_settings
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason, Zone
from aar_api.models.event import Item, Outcome, UsageEvent

ITEM_TYPES = [("A", "Виріб типу А"), ("B", "Виріб типу Б")]
OPERATORS = [(f"E-{i:02d}", f"Експлуатант {i:02d}") for i in range(1, 11)]
LOSS_REASONS = [
    ("a", "Причина a", Zone.EXTERNAL),
    ("b", "Причина b", Zone.EXTERNAL),
    ("c", "Причина c", Zone.OPERATOR),
    ("d", "Причина d", Zone.MANUFACTURER),
    ("e", "Причина e", Zone.UNKNOWN),
]
REPAIR_REASONS = [
    (c, f"Причина {c}", z)
    for c, z in zip(
        "abcdefghijklmnopqr",
        [
            Zone.OPERATOR, Zone.OPERATOR, Zone.MANUFACTURER, Zone.MANUFACTURER,
            Zone.EXTERNAL, Zone.OPERATOR, Zone.MANUFACTURER, Zone.EXTERNAL,
            Zone.OPERATOR, Zone.MANUFACTURER, Zone.OPERATOR, Zone.EXTERNAL,
            Zone.OPERATOR, Zone.MANUFACTURER, Zone.OPERATOR, Zone.EXTERNAL,
            Zone.OPERATOR, Zone.UNKNOWN,
        ],
        strict=True,
    )
]


async def _seed_dict(session: AsyncSession, model: Any, rows: list[tuple]) -> None:
    rows_db: list[Any] = list(await session.scalars(select(model)))
    existing: set[str] = {row.code for row in rows_db}
    for row in rows:
        if row[0] in existing:
            continue
        if len(row) == 2:
            session.add(model(code=row[0], name_uk=row[1]))
        else:
            session.add(model(code=row[0], name_uk=row[1], zone=row[2]))
    await session.flush()


async def _seed_events(session: AsyncSession, rng: random.Random) -> int:
    item_types = {it.code: it.id for it in await session.scalars(select(ItemType))}
    operators = {op.code: op.id for op in await session.scalars(select(Operator))}
    losses = list(await session.scalars(select(LossReason)))
    repairs = list(await session.scalars(select(RepairReason)))

    items_by_type: dict[str, list[Item]] = {"A": [], "B": []}
    serial_counter = 1
    for type_code in ("A", "B"):
        for _ in range(50):
            item = Item(
                serial_no=f"{type_code}-{serial_counter:05d}",
                item_type_id=item_types[type_code],
            )
            session.add(item)
            items_by_type[type_code].append(item)
            serial_counter += 1
    await session.flush()

    created = 0
    day = date(2025, 11, 1)
    end = date(2025, 12, 31)
    while day <= end:
        for op_id in operators.values():
            launches = rng.randint(2, 8)
            for _ in range(launches):
                type_code = rng.choice(("A", "B"))
                item = rng.choice(items_by_type[type_code])
                roll = rng.random()
                outcome: Outcome
                loss_id: int | None = None
                repair_id: int | None = None
                if roll < 0.75:
                    outcome = Outcome.SUCCESS
                elif roll < 0.90:
                    outcome = Outcome.REPAIR
                    repair_id = rng.choice(repairs).id
                else:
                    outcome = Outcome.LOST
                    loss_id = rng.choice(losses).id
                session.add(
                    UsageEvent(
                        item_id=item.id,
                        operator_id=op_id,
                        event_date=day,
                        outcome=outcome,
                        loss_reason_id=loss_id,
                        repair_reason_id=repair_id,
                    )
                )
                created += 1
        day += timedelta(days=1)
    await session.flush()
    return created


async def main() -> None:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    rng = random.Random(42)
    async with Session() as session:
        await _seed_dict(session, ItemType, ITEM_TYPES)
        await _seed_dict(session, Operator, OPERATORS)
        await _seed_dict(session, LossReason, LOSS_REASONS)
        await _seed_dict(session, RepairReason, REPAIR_REASONS)
        if await session.scalar(select(UsageEvent).limit(1)):
            print("Events already seeded, skipping.")
        else:
            n = await _seed_events(session, rng)
            print(f"Created {n} synthetic usage events for Nov-Dec 2025.")
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
