"""Structured donor-story answer evaluator guardrails."""

from __future__ import annotations

import re
from typing import Any, Callable


CONTENT_STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'been', 'but', 'by', 'can',
    'could', 'do', 'for', 'from', 'has', 'have', 'how', 'i', 'if', 'in',
    'is', 'it', 'me', 'my', 'of', 'or', 'that', 'the', 'this', 'to', 'want',
    'what', 'when', 'with', 'would', 'you', 'your',
}

UNSAFE_FOLLOWUP_TERMS = {
    'diagnose', 'treatment plan', 'medicine', 'medication', 'dose', 'dosage',
    'should you', 'should i', 'must you', 'must i',
}


def _normalize(text: str) -> str:
    text = (text or '').lower().strip()
    text = re.sub(r"[^a-z0-9'\s-]", ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _content_words(text: str) -> set[str]:
    return {word for word in _normalize(text).split() if len(word) > 2 and word not in CONTENT_STOPWORDS}


def _valid_followup(question: str, answer: str) -> bool:
    question = (question or '').strip()
    if not 20 <= len(question) <= 220:
        return False
    if question.count('?') != 1 or not question.endswith('?'):
        return False
    normalized = _normalize(question)
    if any(term in normalized for term in UNSAFE_FOLLOWUP_TERMS):
        return False
    return bool(_content_words(question).intersection(_content_words(answer)))


def _validated_candidate(candidate: dict[str, Any], answer: str) -> dict[str, Any]:
    evidence_present = bool(candidate.get('evidence_present'))
    safe_to_advance = bool(candidate.get('safe_to_advance'))
    followup = str(candidate.get('suggested_followup') or '').strip()
    if followup and not _valid_followup(followup, answer):
        followup = ''
    return {
        'evidence_present': evidence_present,
        'safe_to_advance': safe_to_advance,
        'missing_detail': str(candidate.get('missing_detail') or '')[:180],
        'suggested_followup': followup,
    }


def structured_answer_decision(
    step: dict[str, str] | None,
    answer: str,
    heuristic: dict[str, Any],
    evaluator: Callable[[dict[str, str] | None, str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Let a structured evaluator advise sufficiency without owning state transitions."""
    if not step or not evaluator:
        return heuristic
    if heuristic.get('sufficient'):
        return heuristic
    try:
        candidate = evaluator(step, answer, heuristic)
    except Exception as e:
        result = dict(heuristic)
        result['evaluator'] = {'status': 'error', 'reason': type(e).__name__}
        return result
    if not isinstance(candidate, dict):
        return heuristic

    evaluated = _validated_candidate(candidate, answer)
    if evaluated['evidence_present'] and evaluated['safe_to_advance']:
        result = dict(heuristic)
        result.update({
            'sufficient': True,
            'reason': 'structured_evaluator',
            'evaluator': evaluated,
        })
        return result

    result = dict(heuristic)
    result['evaluator'] = evaluated
    if not result.get('sufficient') and evaluated.get('suggested_followup'):
        result['suggested_followup'] = evaluated['suggested_followup']
        result['reason'] = 'structured_evaluator_missing_detail'
    return result
