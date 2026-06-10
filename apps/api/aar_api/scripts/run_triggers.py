"""Evaluate AAR trigger rules T1..T4 and persist new cases.

Usage:
    python -m aar_api.scripts.run_triggers --date 2025-12-15
"""
import argparse
import asyncio
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from aar_api.core.config import get_settings
from aar_api.services.triggers import TriggerConfig, evaluate_triggers


async def run(today: date) -> None:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        created, skipped, auto_validated, regressed = await evaluate_triggers(
            session, today, TriggerConfig()
        )
        await session.commit()
        print(f"Created {len(created)} cases, skipped {skipped} (already exist).")
        print(
            f"Auto-validated {len(auto_validated)} recommendations; "
            f"regressed {len(regressed)} on recurrence."
        )
        for case in created:
            print(f"  #{case.id} [{case.trigger}] {case.title}")
    await engine.dispose()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=datetime.now(UTC).date(),
    )
    args = p.parse_args()
    asyncio.run(run(args.date))


if __name__ == "__main__":
    main()
