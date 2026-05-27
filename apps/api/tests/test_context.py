from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import AARCase, TriggerType
from aar_api.models.dictionaries import LossReason, Zone
from aar_api.schemas.context import ContextAssetDraft
from aar_api.services import llm as llm_service


async def _seed_case() -> int:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add(LossReason(code="a", name_uk="РЕБ", zone=Zone.EXTERNAL))
        case = AARCase(title="Test case", trigger=TriggerType.MSR_DROP)
        s.add(case)
        await s.commit()
        return case.id


async def test_manual_asset_create_starts_draft() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/context/assets",
            json={
                "type": "failure_pattern",
                "title": "Multiple repair returns for same serial within 30 days",
                "description": "Якщо виріб 2+ рази повернувся у ремонт, перевірити вузол живлення.",
                "reusable_for": ["qa_agent", "deployment"],
                "source": "manual",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "draft"
        assert body["source_agent"] == "manual"


async def test_full_lifecycle_draft_validate_deprecate() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        a = (await client.post(
            "/context/assets",
            json={"type": "edge_case", "title": "Cold-start morning launches",
                  "description": "Перші 30 хвилин після увімкнення — підвищена частка lost.",
                  "source": "manual"},
        )).json()
        # validate (dev-mode RBAC permissive)
        r = await client.post(f"/context/assets/{a['id']}/validate")
        assert r.status_code == 200
        assert r.json()["status"] == "validated"
        assert r.json()["validated_at"] is not None

        # successor for deprecation
        b = (await client.post(
            "/context/assets",
            json={"type": "edge_case", "title": "Cold-start morning launches v2",
                  "description": "Уточнено: лише за температури < +5°C.",
                  "source": "manual"},
        )).json()
        await client.post(f"/context/assets/{b['id']}/validate")

        r = await client.post(
            f"/context/assets/{a['id']}/deprecate",
            json={"superseded_by": b["id"]},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "deprecated"
        assert r.json()["superseded_by_id"] == b["id"]


async def test_reject_requires_draft_status() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        a = (await client.post(
            "/context/assets",
            json={"type": "training_gap", "title": "x", "description": "y", "source": "m"},
        )).json()
        # validate it first
        await client.post(f"/context/assets/{a['id']}/validate")
        # now reject must fail with 409
        r = await client.post(
            f"/context/assets/{a['id']}/reject", json={"reason": "no"}
        )
        assert r.status_code == 409


async def test_llm_classify_persists_drafts() -> None:
    await _seed_case()
    fake = llm_service.LLMResult(
        task_output=llm_service.ClassifyResult(
            code="a", confidence=0.95, rationale="РЕБ"
        ),
        context_assets=[
            ContextAssetDraft(
                type="failure_pattern",
                title="REW interference cluster",
                description="3+ події за добу з причиною а — координована РЕБ-атака.",
                reusable_for=["operator_training"],
                confidence=0.8,
            ),
        ],
    )
    with patch.object(llm_service, "classify_reason", return_value=fake):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/llm/classify-reason",
                json={"text": "РЕБ", "kind": "loss"},
            )
            assert r.status_code == 200, r.text
            # verify asset was persisted as draft
            assets = (await client.get("/context/assets", params={"status": "draft"})).json()
            assert any(
                a["source_agent"] == "classify_reason"
                and a["type"] == "failure_pattern"
                for a in assets
            )


async def test_list_filters_by_type_and_status() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/context/assets",
            json={"type": "business_rule", "title": "br", "description": "x", "source": "m"},
        )
        await client.post(
            "/context/assets",
            json={"type": "edge_case", "title": "ec", "description": "y", "source": "m"},
        )
        r = (await client.get("/context/assets", params={"type": "business_rule"})).json()
        assert all(a["type"] == "business_rule" for a in r)
        assert len(r) == 1
