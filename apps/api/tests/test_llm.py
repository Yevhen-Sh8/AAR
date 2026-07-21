from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.config import get_settings
from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import AARCase, TriggerType
from aar_api.models.context import AssetStatus, ContextAsset, ContextAssetType
from aar_api.models.dictionaries import LossReason, Zone
from aar_api.services import llm as llm_service


async def _seed() -> int:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            LossReason(code="a", name_uk="Помилка пуску", zone=Zone.OPERATOR),
            LossReason(code="b", name_uk="РЕБ противника", zone=Zone.EXTERNAL),
        ])
        case = AARCase(title="Зниження MSR_c у E-07", trigger=TriggerType.MSR_DROP)
        s.add(case)
        await s.commit()
        return case.id


async def test_classify_returns_503_when_llm_disabled() -> None:
    get_settings.cache_clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _seed()
        r = await client.post(
            "/llm/classify-reason",
            json={"text": "снаряд РЕБ зніс зв'язок", "kind": "loss"},
        )
        assert r.status_code == 503
        assert "LLM disabled" in r.json()["detail"]


async def test_classify_with_mocked_anthropic() -> None:
    await _seed()

    fake_result = llm_service.LLMResult(
        task_output=llm_service.ClassifyResult(
            code="b", confidence=0.92, rationale="згадка РЕБ → зовнішня зона"
        ),
        context_assets=[],
    )
    with patch.object(llm_service, "classify_reason", return_value=fake_result):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/llm/classify-reason",
                json={"text": "РЕБ зніс ланку звʼязку", "kind": "loss"},
            )
            assert r.status_code == 200, r.text
            assert r.json() == {
                "code": "b",
                "confidence": 0.92,
                "rationale": "згадка РЕБ → зовнішня зона",
            }


async def test_draft_analysis_uses_case_context() -> None:
    case_id = await _seed()
    draft = "## Контекст\nТест.\n## Рекомендації\n1. Довчання."
    fake = llm_service.LLMResult(task_output=draft, context_assets=[])

    with patch.object(llm_service, "draft_case_analysis", return_value=fake) as m:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(f"/llm/cases/{case_id}/draft-analysis")
            assert r.status_code == 200
            assert r.json()["markdown"] == draft
            kwargs = m.call_args.kwargs
            assert kwargs["case_title"] == "Зниження MSR_c у E-07"
            assert kwargs["trigger"] == "msr_drop"


async def test_analogies_returns_empty_when_no_knowledge() -> None:
    """ADR-009: analogies are searched only among VALIDATED context assets.
    With none in the DB, the response is empty."""
    case_id = await _seed()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/llm/cases/{case_id}/analogies")
        assert r.status_code == 200
        assert r.json() == {"matches": []}


async def test_analogies_searches_only_validated_assets() -> None:
    """When a DRAFT and a VALIDATED asset both exist, only the validated one
    is shown to the LLM (regression guard for ADR-009)."""
    case_id = await _seed()
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            ContextAsset(
                type=ContextAssetType.FAILURE_PATTERN,
                title="draft pattern",
                description="should not appear",
                source="test",
                source_agent="test",
                status=AssetStatus.DRAFT,
                reusable_for=["test"],
            ),
            ContextAsset(
                type=ContextAssetType.FAILURE_PATTERN,
                title="valid pattern",
                description="should appear",
                source="test",
                source_agent="test",
                status=AssetStatus.VALIDATED,
                reusable_for=["test"],
            ),
        ])
        await s.commit()

    captured: dict = {}

    def fake_find(query: str, knowledge_entries: list, top_k: int = 3):
        captured["knowledge"] = knowledge_entries
        return llm_service.LLMResult(
            task_output=llm_service.AnalogyResult(matches=[]),
            context_assets=[],
        )

    with patch.object(llm_service, "find_analogies", side_effect=fake_find):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/llm/cases/{case_id}/analogies")
            assert r.status_code == 200
    titles = [k["title"] for k in captured["knowledge"]]
    assert "valid pattern" in titles
    assert "draft pattern" not in titles
