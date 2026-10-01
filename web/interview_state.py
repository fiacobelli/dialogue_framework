"""Code-owned interview skeleton: state, section pointer, recorders, coverage,
progress, and the deterministic safety/operational guards (crisis, skip, no-response).

This is everything code owns; the LLM turn (goal_interview) drives it. story_evidence
and skipped_steps shapes here are exactly what microsite.py consumes.
"""

from __future__ import annotations

import re
from typing import Any

from .config import clean_text as _clean_text
from .interview_flow_config import (
    DECLINE_FOLLOWUP_REPLIES,
    DECLINE_MAX_WORDS,
    DECLINE_PATTERNS,
    GENERATION_REQUIRED_EVIDENCE_GROUPS,
    INTERVIEW_STEPS,
    NO_RESPONSE_SENTINEL,
    PROGRESS_LABELS,
)

# --- Deterministic guards (run before the LLM; never depend on it) ---

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


def is_decline_answer(text: str, awaiting: str | None = None) -> bool:
    """A short "I don't know / rather not / nothing more" reply: the patient must not be probed."""
    normalized = normalize_answer(text)
    if awaiting == 'followup_answer' and normalized in DECLINE_FOLLOWUP_REPLIES:
        return True
    if len(normalized.split()) > DECLINE_MAX_WORDS:
        return False
    return any(re.search(pattern, normalized) for pattern in DECLINE_PATTERNS)


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


# --- Interview state + section pointer ---

def build_interview_state() -> dict[str, Any]:
    """Initial state stored in info_state.user."""
    return {
        'version': 4,
        'step_index': 0,
        'phase': 'INTRO',
        'awaiting': 'name',
        'followup_count': 0,
        'followup_question': None,
        'last_task': 'opening',
        'last_step_id': None,
        'complete': False,
        'story_evidence': {},
        'skipped_steps': {},
        'patient_name': None,
        'patient_name_status': 'missing',
        'patient_name_source': None,
        'last_decision': None,
    }


def normalize_state(state: dict[str, Any] | None) -> dict[str, Any]:
    """Return a current-model state, coercing legacy in-flight pickles."""
    base = build_interview_state()
    if not isinstance(state, dict):
        return base

    base.update(state)
    base['version'] = 4
    if base.get('awaiting') == 'story_answer':
        base['awaiting'] = 'main_answer'
    if base.get('phase') in {'WELCOME', 'BEFORE', 'DURING', 'HOPE'}:
        base['phase'] = 'INTRO' if base.get('awaiting') in {'name', 'readiness'} else 'STORY'
    base.setdefault('story_evidence', {})
    base.setdefault('skipped_steps', {})
    return base


def current_step(state: dict[str, Any]) -> dict[str, str] | None:
    index = int(state.get('step_index') or 0)
    if 0 <= index < len(INTERVIEW_STEPS):
        return INTERVIEW_STEPS[index]
    return None


def progress_snapshot(state: dict[str, Any] | None, phase: str | None = None, photo_count: int = 0) -> dict[str, Any]:
    """Return patient-facing progress metadata for the current interview state."""
    state = normalize_state(state)
    phase = phase or state.get('phase') or 'INTRO'
    total = len(INTERVIEW_STEPS)
    step = current_step(state)
    step_index = int(state.get('step_index') or 0)
    story_step = min(max(step_index + 1, 1), total)

    if phase in {'WELCOME', 'INTRO'}:
        percent = 8 if state.get('awaiting') == 'name' else 14
        current = 0
    elif phase in {'STORY', 'FINAL_DETAILS'}:
        current = story_step
        percent = 15 + round((min(step_index, total - 1) / max(total - 1, 1)) * 65)
    elif phase == 'PHOTOS':
        current = total
        percent = min(92, 82 + max(0, min(photo_count, 3)) * 3)
    elif phase == 'COMPLETE':
        current = total
        percent = 100
    else:
        current = story_step if step else 0
        percent = 20

    return {
        'phase': phase,
        'label': PROGRESS_LABELS.get(phase, 'Interview'),
        'current_step': current,
        'total_steps': total,
        'current_step_id': step.get('id') if step else None,
        'current_step_question': step.get('question') if step else None,
        'percent': max(0, min(100, percent)),
    }


def _advance_step(state: dict[str, Any]) -> dict[str, str] | None:
    state['step_index'] = int(state.get('step_index') or 0) + 1
    state['followup_count'] = 0
    state['followup_question'] = None
    return current_step(state)


def _step_index_for_id(step_id: str) -> int | None:
    for index, step in enumerate(INTERVIEW_STEPS):
        if step.get('id') == step_id:
            return index
    return None


def _generation_evidence_ready(state: dict[str, Any]) -> dict[str, Any]:
    evidence = state.get('story_evidence') or {}
    if not isinstance(evidence, dict):
        evidence = {}
    skipped = state.get('skipped_steps') or {}
    if not isinstance(skipped, dict):
        skipped = {}

    missing = []
    for label, step_ids in GENERATION_REQUIRED_EVIDENCE_GROUPS.items():
        has_accepted = False
        for step_id in step_ids:
            entries = evidence.get(step_id) or []
            if isinstance(entries, dict):
                entries = [entries]
            if any(
                isinstance(entry, dict)
                and entry.get('accepted')
                and _clean_text(entry.get('answer'))
                for entry in entries
            ):
                has_accepted = True
                break
        has_skip = any(step_id in skipped for step_id in step_ids)
        if not has_accepted and not has_skip:
            missing.append(label)
    return {'ready': not missing, 'missing': missing}


def _missing_recovery_step(state: dict[str, Any]) -> tuple[str | None, dict[str, str] | None]:
    readiness = _generation_evidence_ready(state)
    if readiness['ready']:
        return None, None
    for label in readiness['missing']:
        for step_id in GENERATION_REQUIRED_EVIDENCE_GROUPS.get(label, ()):
            index = _step_index_for_id(step_id)
            if index is not None:
                return label, INTERVIEW_STEPS[index]
    return None, None


def _record_story_evidence(
    state: dict[str, Any],
    step: dict[str, str] | None,
    user_input: str,
    decision: dict[str, Any],
    answer_kind: str = 'main_answer',
    question: str | None = None,
) -> None:
    if not step:
        return
    entry = {
        'question': question or step.get('question'),
        'answer': user_input,
        'sufficiency': decision,
        'followup_count': state.get('followup_count', 0),
        'answer_kind': answer_kind,
        'accepted': bool(decision.get('sufficient')),
    }
    evidence = state.setdefault('story_evidence', {})
    step_entries = evidence.setdefault(step['id'], [])
    if isinstance(step_entries, list):
        step_entries.append(entry)
    else:
        evidence[step['id']] = [step_entries, entry]


def _record_skipped_step(state: dict[str, Any], step: dict[str, str] | None, user_input: str, awaiting: str) -> None:
    if not step:
        return
    skipped = state.setdefault('skipped_steps', {})
    skipped[step['id']] = {
        'question': step.get('question'),
        'phase': step.get('phase'),
        'answer_kind': awaiting,
        'reason': 'patient_requested_skip',
        'utterance': user_input,
    }
