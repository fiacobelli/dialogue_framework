"""Bounded emotional-disclosure handling for donor-story interviews."""

from __future__ import annotations

import re
from typing import Any

from .interview_answer_analysis import normalize_answer


EMOTIONAL_SUPPORT_MAX_PER_STEP = 1

CRISIS_PATTERNS = (
    r'\bkill myself\b',
    r'\bend my life\b',
    r'\bhurt myself\b',
    r'\bsuicidal\b',
    r'\bdo not want to live\b',
    r"\bdon't want to live\b",
)

EMOTIONAL_TERMS = {
    'fear': {'scared', 'afraid', 'fear', 'fearful', 'worried', 'anxious', 'nervous', 'terrified'},
    'sadness': {'sad', 'depressed', 'lonely', 'alone', 'hopeless', 'cry', 'crying'},
    'grief': {'grief', 'grieving', 'lost', 'loss', 'died', 'passed away', 'miss'},
    'frustration': {'frustrated', 'angry', 'upset', 'overwhelmed', 'exhausted', 'tired of'},
}

FOLLOWUP_BY_CATEGORY = {
    'fear': 'If you want to share more, what do you wish people understood about that fear?',
    'sadness': 'If you want to share more, what would you want people to understand about that feeling?',
    'grief': 'If you want to share more, how has that loss shaped what this transplant would mean to you?',
    'frustration': 'If you want to share more, what has been the hardest part of carrying that?',
}


def _crisis_detected(text: str) -> bool:
    normalized = normalize_answer(text)
    return any(re.search(pattern, normalized) for pattern in CRISIS_PATTERNS)


def _emotion_category(text: str) -> tuple[str | None, str | None]:
    normalized = normalize_answer(text)
    for category, terms in EMOTIONAL_TERMS.items():
        for term in terms:
            if re.search(rf'\b{re.escape(term)}\b', normalized):
                return category, term
    return None, None


def emotional_support_decision(step: dict[str, str] | None, text: str, state: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded support response when a patient shares distress."""
    if not step:
        return {'should_support': False, 'reason': 'no_step'}

    counts = state.setdefault('emotional_support_count_by_step', {})
    step_id = step['id']
    if int(counts.get(step_id) or 0) >= EMOTIONAL_SUPPORT_MAX_PER_STEP:
        return {'should_support': False, 'reason': 'support_limit_reached'}

    if _crisis_detected(text):
        question = 'Would you like to pause here?'
        return {
            'should_support': True,
            'category': 'crisis',
            'matched': 'crisis',
            'question': question,
            'response': (
                "I'm really sorry you're feeling this. This tool cannot provide crisis support. "
                "If you might hurt yourself, please call or text 988 now, or tell someone near you right away. "
                f"{question}"
            ),
        }

    category, matched = _emotion_category(text)
    if not category:
        return {'should_support': False, 'reason': 'no_emotional_disclosure'}

    question = FOLLOWUP_BY_CATEGORY[category]
    return {
        'should_support': True,
        'category': category,
        'matched': matched,
        'question': question,
        'response': f"Thank you for trusting me with that. {question}",
    }
