"""Generate the monthly AAR report.

Usage:
    python -m aar_api.scripts.monthly_report --year 2025 --month 12 --out /var/aar/reports
"""
import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from aar_api.core.config import get_settings
from aar_api.services.exports import monthly_report_to_pdf, monthly_report_to_xlsx
from aar_api.services.monthly import build_monthly_report


async def run(year: int, month: int, out_dir: Path) -> None:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    out_dir.mkdir(parents=True, exist_ok=True)
    async with Session() as session:
        report = await build_monthly_report(session, year, month)
    await engine.dispose()
    stem = f"monthly-{year}-{month:02d}"
    (out_dir / f"{stem}.xlsx").write_bytes(monthly_report_to_xlsx(report))
    (out_dir / f"{stem}.pdf").write_bytes(monthly_report_to_pdf(report))
    print(f"Wrote {stem}.xlsx and {stem}.pdf to {out_dir}")


def main() -> None:
    now = datetime.now(UTC)
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=now.year if now.month > 1 else now.year - 1)
    p.add_argument("--month", type=int, default=now.month - 1 if now.month > 1 else 12)
    p.add_argument("--out", type=Path, default=Path("out"))
    args = p.parse_args()
    asyncio.run(run(args.year, args.month, args.out))


if __name__ == "__main__":
    main()
