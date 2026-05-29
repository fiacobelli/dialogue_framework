"""Deterministic safety/operational guards for the interview turn.

These run before the LLM and never depend on it: crisis-language detection, the
explicit skip button, and missing/garbled audio. Extracted from the legacy
interview_decision module so the LLM turn keeps its safety floors.
"""

from __future__ import annotations

import re
from typing import Any

from .interview_flow_config import NO_RESPONSE_SENTINEL

CRISIS_PATTERNS = (
    r'\bkill myself\b',
    r'\bend my life\b',
    r'\bhurt myself\b',
    r'\bsuicidal\b',
    r'\bdo not want to live\b',
    r"\bdon't want to live\b",
)


def normalize_answer(text: str) -> str:
    text = (text or '').lower().strip()
    text = re.sub(r"[^a-z0-9'\s-]", ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def is_skip_intent(text: str, turn_meta: dict[str, Any] | None = None) -> bool:
    """Only an explicit UI skip event can skip a required story section."""
    return bool((turn_meta or {}).get('skip_requested'))


def _crisis_detected(text: str, turn_meta: dict[str, Any] | None = None) -> bool:
    """Deterministic crisis-language guard (safety floor)."""
    normalized = normalize_answer(text)
    return any(re.search(pattern, normalized) for pattern in CRISIS_PATTERNS)


def input_guard_decision(step: dict[str, str] | None, text: str, turn_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Detect system-level input failures without guessing patient meaning."""
    normalized = normalize_answer(text)
    words = normalized.split()
    turn_meta = turn_meta or {}

    if turn_meta.get('no_response') or normalized == normalize_answer(NO_RESPONSE_SENTINEL) or not normalized:
        return {'repair': True, 'reason': 'empty_or_no_response', 'matched': normalized}

    try:
        confidence = turn_meta.get('speech_confidence')
        low_confidence = confidence is not None and float(confidence) > 0 and float(confidence) < 0.45
    except (TypeError, ValueError):
        low_confidence = False
    if low_confidence and len(words) < 5:
        return {'repair': True, 'reason': 'low_confidence_fragment', 'matched': normalized}
    return {'repair': False, 'reason': 'answer_candidate', 'matched': normalized}
