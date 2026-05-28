from io import BytesIO

from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.dictionaries import ItemType, LossReason, Operator, Zone


async def _seed_dicts() -> None:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            ItemType(code="A", name_uk="Виріб А"),
            ItemType(code="B", name_uk="Виріб Б"),
            Operator(code="E-01", name_uk="Експл. 01"),
            Operator(code="E-02", name_uk="Експл. 02"),
            LossReason(code="a", name_uk="РЕБ", zone=Zone.EXTERNAL),
        ])
        await s.commit()


async def _post_csv(client: AsyncClient, csv_text: str, *, dry_run: bool = False):
    files = {"file": ("events.csv", csv_text.encode("utf-8"), "text/csv")}
    return await client.post(
        "/events/import", files=files, params={"dry_run": str(dry_run).lower()}
    )


async def test_import_csv_happy_path() -> None:
    await _seed_dicts()
    csv = (
        "item_serial_no,item_type_code,operator_code,event_date,outcome,"
        "loss_reason_code,repair_reason_code,notes\n"
        "A-00001,A,E-01,2025-11-15,success,,,\n"
        "A-00002,A,E-01,2025-11-15,lost,a,,Помилка пуску\n"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await _post_csv(client, csv)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_rows"] == 2
        assert body["imported"] == 2
        assert body["duplicates"] == 0
        assert body["failed"] == 0
        assert body["dry_run"] is False


async def test_import_csv_dry_run_does_not_persist() -> None:
    await _seed_dicts()
    csv = (
        "item_serial_no,item_type_code,operator_code,event_date,outcome\n"
        "A-00099,A,E-02,2025-11-20,success\n"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await _post_csv(client, csv, dry_run=True)
        body = r.json()
        assert body["parsed"] == 1
        assert body["imported"] == 0  # dry run
        # Confirm not persisted:
        events = (await client.get("/events")).json()
        assert all(e["item_id"] != 1 or True for e in events)
        assert len(events) == 0


async def test_import_csv_reports_row_errors() -> None:
    await _seed_dicts()
    csv = (
        "item_serial_no,item_type_code,operator_code,event_date,outcome\n"
        "A-1,A,E-01,2025-11-15,success\n"           # OK
        "A-2,A,E-01,INVALID-DATE,success\n"          # bad date
        "A-3,A,E-01,2025-11-15,wat\n"                # bad outcome
        "A-4,A,E-01,2025-11-15,lost\n"               # lost without reason_code
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await _post_csv(client, csv)
        body = r.json()
        assert body["total_rows"] == 4
        assert body["imported"] == 1
        assert body["failed"] == 3
        errs = [e["message"] for e in body["parse_errors"]]
        assert any("event_date" in m for m in errs)
        assert any("outcome must be one of" in m for m in errs)


async def test_import_idempotent_via_client_event_id() -> None:
    await _seed_dicts()
    csv = (
        "item_serial_no,item_type_code,operator_code,event_date,outcome,"
        "client_event_id\n"
        "A-X,A,E-01,2025-11-15,success,uuid-import-1\n"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = (await _post_csv(client, csv)).json()
        assert first["imported"] == 1 and first["duplicates"] == 0
        second = (await _post_csv(client, csv)).json()
        assert second["imported"] == 0 and second["duplicates"] == 1


async def test_import_csv_missing_required_column() -> None:
    await _seed_dicts()
    csv = "item_serial_no,outcome\nA-1,success\n"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await _post_csv(client, csv)
        body = r.json()
        assert body["total_rows"] == 0
        assert body["failed"] == 1
        assert "missing required columns" in body["parse_errors"][0]["message"]


async def test_import_xlsx_happy_path() -> None:
    await _seed_dicts()
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append([
        "item_serial_no", "item_type_code", "operator_code",
        "event_date", "outcome", "loss_reason_code",
    ])
    ws.append(["B-001", "B", "E-02", "2025-11-15", "success", None])
    ws.append(["B-002", "B", "E-02", "2025-11-16", "lost", "a"])
    buf = BytesIO()
    wb.save(buf)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "file": (
                "import.xlsx", buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        }
        r = await client.post("/events/import", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_rows"] == 2
        assert body["imported"] == 2


async def test_import_unsupported_extension() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("data.txt", b"foo,bar\n1,2\n", "text/plain")}
        r = await client.post("/events/import", files=files)
        body = r.json()
        assert body["failed"] == 1
        assert "unsupported file type" in body["parse_errors"][0]["message"]
