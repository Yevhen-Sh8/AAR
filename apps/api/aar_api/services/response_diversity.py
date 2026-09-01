"""Does the unit answer the same trigger the same way every time? (ADR-026)

The Parallax concept was «anti-predictability»: a unit whose reaction to a
given situation never varies can be read by anyone watching it. The mechanism
they proposed — require every recommendation to carry two or more equivalent
variants — we deliberately did NOT build. Demanding a second option produces
one of two things: an invented alternative where the evidence supports only one
course of action, or an empty checkbox. Manufacturing content is the failure
this project has spent its whole life removing.

What IS honestly measurable is the repetition itself. If the same remedial
action is issued to the same operator for the same trigger again and again,
that is a fact in the data, not an inference about the adversary. This module
reports that fact and says nothing about what an enemy can or cannot predict —
the reader draws that conclusion, because the reader knows the operational
picture and we do not.

Note the deliberate distinction from `recurrence_rate`: recurrence asks whether
a FIX FAILED (the problem came back). This asks whether the RESPONSE IS
FORMULAIC (the answer never changes). A perfectly effective, never-regressing
recommendation can still be perfectly predictable.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.models.aar import AARCase, Recommendation
from aar_api.models.dictionaries import Operator

#: Below this many cases the pattern is noise, not a habit.
MIN_CASES = 3
#: Share of responses that must fall on one action before it is worth naming.
DOMINANT_SHARE_THRESHOLD = 0.8

_PUNCT = re.compile(r"[.,;:!?«»\"'()\[\]-]+")
_SPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Fold trivial wording differences so «Провести інструктаж.» matches
    «провести  інструктаж».

    Kept deliberately shallow. Aggressive normalisation (stemming, synonyms)
    would collapse two genuinely different actions into one and manufacture a
    finding — the exact error this module exists to avoid.
    """
    return _SPACE.sub(" ", _PUNCT.sub(" ", text.casefold())).strip()


@dataclass(frozen=True)
class ResponsePattern:
    operator_code: str | None
    trigger: str
    cases: int
    recommendations: int
    distinct_responses: int
    dominant_text: str
    dominant_count: int
    dominant_share: float


async def compute_response_patterns(
    session: AsyncSession,
    period_from: datetime | None = None,
    period_to: datetime | None = None,
    *,
    min_cases: int = MIN_CASES,
    share_threshold: float = DOMINANT_SHARE_THRESHOLD,
) -> list[ResponsePattern]:
    """Group by (operator, trigger); report where one action dominates.

    Only pairs with at least `min_cases` cases are considered — twice is a
    coincidence, and calling it a habit would be the same overreach as a
    fabricated trend line.
    """
    period_to = period_to or datetime.now(UTC)
    period_from = period_from or period_to - timedelta(days=365)

    rows = (
        await session.execute(
            select(AARCase, Recommendation.text, Operator.code)
            .join(Recommendation, Recommendation.case_id == AARCase.id)
            .join(Operator, Operator.id == AARCase.operator_id, isouter=True)
            .where(AARCase.opened_at >= period_from, AARCase.opened_at <= period_to)
        )
    ).all()

    # (operator_code, trigger) → {normalised text: [original texts]}, plus case ids
    grouped: dict[tuple[str | None, str], dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    case_ids: dict[tuple[str | None, str], set[int]] = defaultdict(set)
    for case, text, operator_code in rows:
        key = (operator_code, case.trigger.value)
        grouped[key][normalise(text)].append(text)
        case_ids[key].add(case.id)

    out: list[ResponsePattern] = []
    for key, by_text in grouped.items():
        operator_code, trigger = key
        cases = len(case_ids[key])
        if cases < min_cases:
            continue
        total = sum(len(v) for v in by_text.values())
        if total == 0:
            continue
        dominant_norm = max(by_text, key=lambda k: len(by_text[k]))
        dominant_count = len(by_text[dominant_norm])
        share = dominant_count / total
        if share < share_threshold:
            continue
        out.append(
            ResponsePattern(
                operator_code=operator_code,
                trigger=trigger,
                cases=cases,
                recommendations=total,
                distinct_responses=len(by_text),
                # Show the wording a person actually wrote, not the folded form.
                dominant_text=by_text[dominant_norm][0],
                dominant_count=dominant_count,
                dominant_share=round(share, 3),
            )
        )

    # Most entrenched first: more repetitions of one action matter more than a
    # high share over few cases.
    out.sort(key=lambda p: (p.dominant_count, p.dominant_share), reverse=True)
    return out
