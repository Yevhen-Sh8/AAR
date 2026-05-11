from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from aar_api.core.config import get_settings
from aar_api.core.db import _engine
from aar_api.main import app
from aar_api.models.aar import AARCase, KnowledgeEntry, TriggerType
from aar_api.models.dictionaries import LossReason, Zone
from aar_api.services import llm as llm_service


async def _seed() -> int:
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        s.add_all([
            LossReason(code="a", name_uk="Помилка пуску", zone=Zone.OPERATOR),
            LossReason(code="b", name_uk="РЕБ противника", zone=Zone.EXTERNAL),
            KnowledgeEntry(title="Test", content="Old case content"),
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

    fake_result = llm_service.ClassifyResult(
        code="b", confidence=0.92, rationale="згадка РЕБ → зовнішня зона"
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

    with patch.object(llm_service, "draft_case_analysis", return_value=draft) as m:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(f"/llm/cases/{case_id}/draft-analysis")
            assert r.status_code == 200
            assert r.json()["markdown"] == draft
            kwargs = m.call_args.kwargs
            assert kwargs["case_title"] == "Зниження MSR_c у E-07"
            assert kwargs["trigger"] == "msr_drop"


async def test_analogies_returns_empty_when_no_knowledge() -> None:
    case_id = await _seed()
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as s:
        from sqlalchemy import delete

        await s.execute(delete(KnowledgeEntry))
        await s.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/llm/cases/{case_id}/analogies")
        assert r.status_code == 200
        assert r.json() == {"matches": []}
