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
    # Evidence provenance: the reader must be able to see how much testimony
    # the draft actually rests on, not just that a model wrote it.
    reports_used: int = 0
    reports_pending: int = 0


class AnalogyMatchOut(BaseModel):
    knowledge_id: int
    relevance: float
    rationale: str


class AnalogyResponse(BaseModel):
    matches: list[AnalogyMatchOut]
