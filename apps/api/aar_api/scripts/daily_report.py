"""Generate the daily AAR report.

Usage:
    python -m aar_api.scripts.daily_report --date 2025-11-15 --out /var/aar/reports
    python -m aar_api.scripts.daily_report  # defaults to yesterday, ./out
"""
import argparse
import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from aar_api.core.config import get_settings
from aar_api.services.exports import daily_report_to_pdf, daily_report_to_xlsx
from aar_api.services.reports import build_daily_report


async def run(report_date: date, out_dir: Path) -> None:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    out_dir.mkdir(parents=True, exist_ok=True)
    async with Session() as session:
        report = await build_daily_report(session, report_date)
    await engine.dispose()

    stem = f"daily-{report_date.isoformat()}"
    (out_dir / f"{stem}.xlsx").write_bytes(daily_report_to_xlsx(report))
    (out_dir / f"{stem}.pdf").write_bytes(daily_report_to_pdf(report))
    print(f"Wrote {stem}.xlsx and {stem}.pdf to {out_dir}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=(datetime.now(UTC).date() - timedelta(days=1)),
    )
    p.add_argument("--out", type=Path, default=Path("out"))
    args = p.parse_args()
    asyncio.run(run(args.date, args.out))


if __name__ == "__main__":
    main()
