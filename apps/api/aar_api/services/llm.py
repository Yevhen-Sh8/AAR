"""LLM automation: A8 cause classification, A9 analysis draft, A10 analogy search.

v1.1 (Context Accumulation Layer):
Every function now returns LLMResult[T] = (task_output, context_assets[]).
Context assets are created as DRAFT — never auto-validated (ADR-008).

Backed by the Anthropic SDK. Sonnet 4.6 default; Haiku 4.5 for mass
classification. Static context (rubric + reason catalog) is sent with
cache_control=ephemeral so repeated calls hit the prefix cache.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

from aar_api.core.config import get_settings
from aar_api.schemas.context import ContextAssetDraft

logger = logging.getLogger(__name__)


# -------------------- v1.1: dual-result envelope --------------------------


@dataclass
class LLMResult[T]:
    task_output: T
    context_assets: list[ContextAssetDraft] = field(default_factory=list)


# -------------------- system prompts --------------------------------------

_ASSET_TYPES = (
    "business_rule | failure_pattern | edge_case | acceptance_criterion | "
    "architectural_decision | deployment_lesson | operator_practice | training_gap"
)

CLASSIFY_SYSTEM = f"""\
Ти — асистент-класифікатор причин подій з виробами.

Відповідь — у форматі JSON за схемою. Поле `code` — код зі словника, який буде
надано (або "unknown" якщо опис не співпадає, тоді confidence ≤ 0.4).

Додатково — поле `context_assets`: список knowledge-fragments, які ти виявив у
описі і які варто зберегти для майбутніх задач (failure_pattern, edge_case,
training_gap тощо). Типи: {_ASSET_TYPES}. Якщо нічого не виявлено — порожній
список. НЕ позначай активи як validated — це робить людина.
"""

ANALYST_SYSTEM = f"""\
Ти — старший аналітик AAR (After Action Review). На основі агрегованих даних
та індивідуальних звітів учасників сформуй проект підсумкового аналізу
менеджера.

Відповідь — JSON: поля `markdown` (структурований текст: контекст / що сталося /
чому / що спрацювало / що не спрацювало / рекомендації) і `context_assets`
(reusable knowledge fragments, типи: {_ASSET_TYPES}).

Тон — стислий, без води. Українською мовою. Активи лишай як draft — людина їх
валідує окремо.
"""

ANALOGY_SYSTEM = f"""\
Тобі дано опис нового AAR-кейсу та список історичних записів бази знань.

Поверни JSON: поля `matches` (top-N найрелевантніших, з knowledge_id /
relevance / rationale) та `context_assets` (нові закономірності-фрагменти, які
ти помітив, порівнюючи кейс із базою; типи: {_ASSET_TYPES}). Активи — draft.
"""


# -------------------- task-output models ----------------------------------

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


# -------------------- shared schemas for output_config --------------------

_ASSETS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "reusable_for": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
        },
        "required": ["type", "title", "description", "reusable_for"],
        "additionalProperties": False,
    },
}


def _client() -> anthropic.Anthropic:
    s = get_settings()
    if not s.llm_enabled or not s.anthropic_api_key:
        raise RuntimeError(
            "LLM disabled. Set AAR_LLM_ENABLED=true and AAR_ANTHROPIC_API_KEY."
        )
    return anthropic.Anthropic(api_key=s.anthropic_api_key)


def _catalog_text(catalog: Iterable[ReasonCatalogEntry]) -> str:
    return "\n".join(f"- {e.code} | зона={e.zone} | {e.name_uk}" for e in catalog)


def _parse_assets(raw: list[dict[str, Any]] | None) -> list[ContextAssetDraft]:
    if not raw:
        return []
    out: list[ContextAssetDraft] = []
    for item in raw:
        try:
            out.append(ContextAssetDraft.model_validate(item))
        except ValidationError as e:
            logger.warning("llm: malformed context asset skipped — %s: %s", e, item)
    return out


def _log_cache(response: Any, where: str) -> None:
    usage = response.usage
    logger.info(
        "llm.%s cache_read=%s cache_write=%s",
        where,
        getattr(usage, "cache_read_input_tokens", None),
        getattr(usage, "cache_creation_input_tokens", None),
    )


# -------------------- A8: classify ----------------------------------------

def classify_reason(
    free_text: str,
    catalog: list[ReasonCatalogEntry],
    *,
    kind: str,
    use_fast_model: bool = True,
) -> LLMResult[ClassifyResult]:
    s = get_settings()
    client = _client()
    model = s.llm_fast_model if use_fast_model else s.llm_default_model

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
            "context_assets": _ASSETS_SCHEMA,
        },
        "required": ["code", "confidence", "rationale", "context_assets"],
        "additionalProperties": False,
    }
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=[
            {"type": "text", "text": CLASSIFY_SYSTEM},
            {"type": "text", "text": catalog_block, "cache_control": {"type": "ephemeral"}},
        ],
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": f"Опис події:\n{free_text}"}],
    )
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    _log_cache(response, "classify")
    return LLMResult(
        task_output=ClassifyResult(
            code=data["code"], confidence=data["confidence"], rationale=data["rationale"]
        ),
        context_assets=_parse_assets(data.get("context_assets")),
    )


# -------------------- A9: draft analysis ----------------------------------

def draft_case_analysis(
    *,
    case_title: str,
    trigger: str,
    operator_code: str | None,
    events_summary: str,
    individual_reports: list[dict[str, str | None]],
) -> LLMResult[str]:
    client = _client()
    s = get_settings()
    payload = {
        "case_title": case_title,
        "trigger": trigger,
        "operator_code": operator_code,
        "events_summary": events_summary,
        "individual_reports": individual_reports,
    }
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "markdown": {"type": "string"},
            "context_assets": _ASSETS_SCHEMA,
        },
        "required": ["markdown", "context_assets"],
        "additionalProperties": False,
    }
    response = client.messages.create(
        model=s.llm_default_model,
        max_tokens=4096,
        system=[
            {"type": "text", "text": ANALYST_SYSTEM, "cache_control": {"type": "ephemeral"}},
        ],
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[
            {
                "role": "user",
                "content": (
                    "Сформуй проект підсумкового аналізу для кейсу (вхід JSON):\n\n"
                    f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
                ),
            }
        ],
    )
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    _log_cache(response, "draft")
    return LLMResult(
        task_output=data["markdown"],
        context_assets=_parse_assets(data.get("context_assets")),
    )


# -------------------- A10: analogies --------------------------------------

def find_analogies(
    *,
    query: str,
    knowledge_entries: list[dict[str, str | int]],
    top_k: int = 3,
) -> LLMResult[AnalogyResult]:
    client = _client()
    s = get_settings()
    schema: dict[str, Any] = {
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
            },
            "context_assets": _ASSETS_SCHEMA,
        },
        "required": ["matches", "context_assets"],
        "additionalProperties": False,
    }
    catalog_block = "База знань (id | title | content):\n" + "\n".join(
        f"#{e['id']} | {e['title']} | {e['content']}" for e in knowledge_entries
    )
    response = client.messages.create(
        model=s.llm_default_model,
        max_tokens=2048,
        system=[
            {"type": "text", "text": ANALOGY_SYSTEM},
            {"type": "text", "text": catalog_block, "cache_control": {"type": "ephemeral"}},
        ],
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[
            {
                "role": "user",
                "content": f"Знайди top-{top_k} аналогів для нового кейсу:\n{query}",
            }
        ],
    )
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    _log_cache(response, "analogies")
    return LLMResult(
        task_output=AnalogyResult(
            matches=[AnalogyMatch(**m) for m in data["matches"]],
        ),
        context_assets=_parse_assets(data.get("context_assets")),
    )
