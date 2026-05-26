"""Pre-evidence interpretation for donor-story interview turns."""

from __future__ import annotations

import re
from typing import Any

from .interview_answer_analysis import normalize_answer

PRIOR_REFERENCE_PATTERNS = (
    r'\bi (already|previously) (said|mentioned|told|answered)\b',
    r'\bi did (say|mention|tell|answer) (that|this|it)\b',
    r'\b(as|like) i (said|mentioned|told you)\b',
    r'\bmentioned it before\b',
    r'\bsaid it before\b',
    r'\balready (said|mentioned|answered|told you)\b',
)


def _accepted_evidence_for_step(state: dict[str, Any], step_id: str | None) -> list[dict[str, Any]]:
    if not step_id:
        return []
    entries = (state.get('story_evidence') or {}).get(step_id) or []
    if isinstance(entries, dict):
        entries = [entries]
    return [entry for entry in entries if isinstance(entry, dict) and entry.get('accepted')]


def interpret_story_turn(
    step: dict[str, str] | None,
    state: dict[str, Any],
    text: str,
    awaiting: str,
) -> dict[str, Any]:
    """Classify a story turn before it can be stored as evidence."""
    normalized = normalize_answer(text)
    step_id = step.get('id') if step else None
    accepted = _accepted_evidence_for_step(state, step_id)

    if normalized and any(re.search(pattern, normalized) for pattern in PRIOR_REFERENCE_PATTERNS):
        return {
            'category': 'prior_reference',
            'evidence_worthy': False,
            'reason': 'patient_referred_to_prior_answer',
            'matched': normalized,
            'awaiting': awaiting,
            'step_id': step_id,
            'accepted_evidence_count': len(accepted),
            'current_step_has_accepted_evidence': bool(accepted),
        }

    return {
        'category': 'answer_candidate',
        'evidence_worthy': True,
        'reason': 'default_story_turn',
        'matched': normalized,
        'awaiting': awaiting,
        'step_id': step_id,
        'accepted_evidence_count': len(accepted),
        'current_step_has_accepted_evidence': bool(accepted),
    }
