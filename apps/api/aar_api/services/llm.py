"""LLM automation: A8 cause classification, A9 analysis draft, A10 analogy search.

Backed by the Anthropic SDK. Sonnet 4.6 is the default; Haiku 4.5 handles the
mass-classification endpoint. Static context (rubric + reason catalog) is sent
with cache_control=ephemeral so repeated calls hit the prefix cache.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import anthropic
from pydantic import BaseModel

from aar_api.core.config import get_settings

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM = """\
Ти — асистент-класифікатор причин, що супроводжують події використання
виробів. Твоє завдання — віднести вільнотекстовий опис до одного з кодів
причин зі словника, який буде наданий. Відповідай у форматі JSON, дотримуйся
схеми. Якщо опис не співпадає з жодним кодом — використовуй "unknown" і
постав confidence ≤ 0.4.
"""

ANALYST_SYSTEM = """\
Ти — старший аналітик AAR (After Action Review). На основі агрегованих
даних та індивідуальних звітів учасників сформуй проект підсумкового
аналізу для менеджера. Структура: (1) Контекст, (2) Що сталося, (3) Чому,
(4) Що спрацювало, (5) Що не спрацювало, (6) Рекомендації (3–5 пунктів).
Тон — стислий, без води. Українською мовою.
"""

ANALOGY_SYSTEM = """\
Тобі дано опис нового AAR-кейсу та список історичних записів бази знань.
Поверни JSON зі списком top-N найрелевантніших записів за порядком
спадання релевантності з коротким поясненням, чому саме цей запис
аналогічний.
"""


class ClassifyResult(BaseModel):
    code: str
    confidence: float
    rationale: str


class AnalogyMatch(BaseModel):
    knowledge_id: int
    relevance: float
    rationale: str


class AnalogyResult(BaseModel):
    matches: list[AnalogyMatch]


@dataclass(frozen=True)
class ReasonCatalogEntry:
    code: str
    name_uk: str
    zone: str


def _client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.llm_enabled or not settings.anthropic_api_key:
        raise RuntimeError(
            "LLM disabled. Set AAR_LLM_ENABLED=true and AAR_ANTHROPIC_API_KEY."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _catalog_text(catalog: Iterable[ReasonCatalogEntry]) -> str:
    return "\n".join(
        f"- {e.code} | зона={e.zone} | {e.name_uk}" for e in catalog
    )


def classify_reason(
    free_text: str,
    catalog: list[ReasonCatalogEntry],
    *,
    kind: str,
    use_fast_model: bool = True,
) -> ClassifyResult:
    """Map free-text reason to a catalog code.

    `kind` ∈ {"loss", "repair"} only changes the user-facing label.
    Reason catalog goes into the cached prefix; volatile free-text comes last.
    """
    settings = get_settings()
    client = _client()
    model = settings.llm_fast_model if use_fast_model else settings.llm_default_model

    catalog_block = (
        f"Тип події: {kind} (втрата=loss / ремонт=repair).\n"
        f"Доступні коди причин:\n{_catalog_text(catalog)}\n"
    )
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "confidence": {"type": "number"},
            "rationale": {"type": "string"},
        },
        "required": ["code", "confidence", "rationale"],
        "additionalProperties": False,
    }

    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=[
            {"type": "text", "text": CLASSIFY_SYSTEM},
            {"type": "text", "text": catalog_block, "cache_control": {"type": "ephemeral"}},
        ],
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": f"Опис події:\n{free_text}"}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    logger.info(
        "llm.classify cache_read=%s cache_write=%s",
        response.usage.cache_read_input_tokens,
        response.usage.cache_creation_input_tokens,
    )
    return ClassifyResult(**data)


def draft_case_analysis(
    *,
    case_title: str,
    trigger: str,
    operator_code: str | None,
    events_summary: str,
    individual_reports: list[dict[str, str | None]],
) -> str:
    """Return a Markdown draft of the manager's analysis for a case."""
    client = _client()
    settings = get_settings()
    payload = {
        "case_title": case_title,
        "trigger": trigger,
        "operator_code": operator_code,
        "events_summary": events_summary,
        "individual_reports": individual_reports,
    }

    response = client.messages.create(
        model=settings.llm_default_model,
        max_tokens=2048,
        system=[
            {"type": "text", "text": ANALYST_SYSTEM, "cache_control": {"type": "ephemeral"}},
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    "Сформуй проект підсумкового аналізу для наступного "
                    "AAR-кейсу (вхід у JSON):\n\n"
                    f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
                ),
            }
        ],
    )
    return next(b.text for b in response.content if b.type == "text")


def find_analogies(
    *,
    query: str,
    knowledge_entries: list[dict[str, str | int]],
    top_k: int = 3,
) -> AnalogyResult:
    """Rank historical KnowledgeEntry rows by relevance to a new case."""
    client = _client()
    settings = get_settings()
    schema = {
        "type": "object",
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "knowledge_id": {"type": "integer"},
                        "relevance": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["knowledge_id", "relevance", "rationale"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["matches"],
        "additionalProperties": False,
    }
    catalog_block = (
        "База знань (id | title | content):\n"
        + "\n".join(
            f"#{e['id']} | {e['title']} | {e['content']}" for e in knowledge_entries
        )
    )
    response = client.messages.create(
        model=settings.llm_default_model,
        max_tokens=1024,
        system=[
            {"type": "text", "text": ANALOGY_SYSTEM},
            {"type": "text", "text": catalog_block, "cache_control": {"type": "ephemeral"}},
        ],
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Знайди top-{top_k} аналогів для нового кейсу:\n{query}"
                ),
            }
        ],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return AnalogyResult(**json.loads(text))
