from typing import Literal

from pydantic import BaseModel


class ClassifyRequest(BaseModel):
    text: str
    kind: Literal["loss", "repair"]
    use_fast_model: bool = True


class ClassifyResponse(BaseModel):
    code: str
    confidence: float
    rationale: str


class DraftAnalysisResponse(BaseModel):
    markdown: str


class AnalogyMatchOut(BaseModel):
    knowledge_id: int
    relevance: float
    rationale: str


class AnalogyResponse(BaseModel):
    matches: list[AnalogyMatchOut]
