"""Bounded evidence interpretation for the web NLU layer.

This module classifies patient language into structured evidence. It must not
choose app actions or transition interview state.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import EVIDENCE_INTERPRETER_PROMPT_VERSION, LLM_ERROR_MESSAGE
from .interview_flow_config import INTERVIEW_STEPS


SCHEMA_VERSION = 1
INPUT_QUALITIES = {'answer', 'clarification', 'operational_issue', 'non_answer', 'unclear'}
STEP_STATUSES = {'sufficient', 'thin', 'not_addressed', 'explicit_none'}
READINESS_VALUES = {'ready', 'not_ready', 'question', 'unclear', ''}


def empty_evidence_frame(reason: str = 'not_run') -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'prompt_version': EVIDENCE_INTERPRETER_PROMPT_VERSION,
        'valid': False,
        'fallback_reason': reason,
        'input_quality': 'unclear',
        'input_quality_confidence': 0.0,
        'safety': {'crisis': False, 'confidence': 0.0},
        'current_step': {
            'step_id': None,
            'status': 'not_addressed',
            'summary': '',
            'confidence': 0.0,
        },
        'future_evidence': [],
        'slots': {},
        'final_nothing_else': False,
        'already_answered_current': False,
    }


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _text(value: Any, limit: int = 500) -> str:
    return str(value or '').strip()[:limit]


def _step_ids() -> set[str]:
    return {step['id'] for step in INTERVIEW_STEPS}


def _step_frame(value: Any, *, default_step_id: str | None = None) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    step_id = value.get('step_id') if value.get('step_id') in _step_ids() else default_step_id
    status = value.get('status') if value.get('status') in STEP_STATUSES else 'not_addressed'
    return {
        'step_id': step_id,
        'status': status,
        'summary': _text(value.get('summary')),
        'confidence': _confidence(value.get('confidence')),
    }


def validate_evidence_frame(data: Any, current_step_id: str | None = None) -> dict[str, Any]:
    """Return a sanitized evidence frame or raise ValueError."""
    if not isinstance(data, dict):
        raise ValueError('frame_not_object')
    if int(data.get('schema_version') or 0) != SCHEMA_VERSION:
        raise ValueError('schema_version_mismatch')

    input_quality = data.get('input_quality')
    if input_quality not in INPUT_QUALITIES:
        input_quality = 'unclear'

    safety = data.get('safety') if isinstance(data.get('safety'), dict) else {}
    future = []
    for item in data.get('future_evidence') or []:
        frame = _step_frame(item)
        if frame['step_id']:
            future.append(frame)
    slots = data.get('slots') if isinstance(data.get('slots'), dict) else {}
    public_name = _text(slots.get('public_name'), 80)
    public_name = re.sub(r'\s+', ' ', public_name).strip()
    if len(public_name.split()) > 5:
        public_name = ''
    readiness = _text(slots.get('readiness'), 20).lower()
    if readiness not in READINESS_VALUES:
        readiness = ''

    return {
        'schema_version': SCHEMA_VERSION,
        'prompt_version': _text(data.get('prompt_version') or EVIDENCE_INTERPRETER_PROMPT_VERSION, 80),
        'valid': True,
        'fallback_reason': '',
        'input_quality': input_quality,
        'input_quality_confidence': _confidence(data.get('input_quality_confidence')),
        'safety': {
            'crisis': bool(safety.get('crisis')),
            'confidence': _confidence(safety.get('confidence')),
        },
        'current_step': _step_frame(data.get('current_step'), default_step_id=current_step_id),
        'future_evidence': future,
        'slots': {
            'public_name': public_name,
            'public_name_confidence': _confidence(slots.get('public_name_confidence')),
            'readiness': readiness,
            'readiness_confidence': _confidence(slots.get('readiness_confidence')),
        },
        'final_nothing_else': bool(data.get('final_nothing_else')),
        'already_answered_current': bool(data.get('already_answered_current')),
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or '').strip()
    if text == LLM_ERROR_MESSAGE:
        raise ValueError('llm_error')
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end >= start:
        text = text[start:end + 1]
    return json.loads(text)


class EvidenceInterpreter:
    """LLM-backed evidence classifier with strict schema validation."""

    def __init__(self, llm_provider):
        self.llm = llm_provider

    def interpret(
        self,
        text: str,
        step: dict[str, str] | None,
        state: dict[str, Any],
        turn_meta: dict[str, Any] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        step_id = step.get('id') if step else None
        try:
            prompt = self._prompt(text, step, state, turn_meta)
            raw = self.llm.generate(
                [{'role': 'user', 'content': prompt}],
                'Return only valid JSON for the requested evidence schema.',
            )
            frame = validate_evidence_frame(_extract_json(raw), current_step_id=step_id)
            frame['mode'] = 'llm'
            return frame
        except Exception as exc:
            frame = empty_evidence_frame(f'interpreter_error:{type(exc).__name__}')
            frame['current_step']['step_id'] = step_id
            frame['mode'] = 'fallback'
            return frame

    def _prompt(
        self,
        text: str,
        step: dict[str, str] | None,
        state: dict[str, Any],
        turn_meta: dict[str, Any] | None = None,
    ) -> str:
        steps = [
            {'id': item['id'], 'question': item['question'], 'focus': item['focus'], 'required': item['required']}
            for item in INTERVIEW_STEPS
        ]
        evidence = state.get('story_evidence') or {}
        compact_evidence = {
            key: [
                {'answer': _text(entry.get('answer'), 180), 'accepted': bool(entry.get('accepted'))}
                for entry in (value if isinstance(value, list) else [value])
                if isinstance(entry, dict)
            ][-2:]
            for key, value in evidence.items()
        }
        return (
            'You are a bounded NLU evidence classifier for a kidney donor-story interview.\n'
            'Return JSON only. Do not choose app actions. Do not decide whether to advance, skip, publish, or close.\n'
            f'Use schema_version {SCHEMA_VERSION} and prompt_version "{EVIDENCE_INTERPRETER_PROMPT_VERSION}".\n'
            'Allowed input_quality values: answer, clarification, operational_issue, non_answer, unclear.\n'
            'Allowed status values: sufficient, thin, not_addressed, explicit_none.\n\n'
            'Classify the latest user answer into evidence for the current step and any future steps.\n'
            'Set input_quality_confidence from 0 to 1.\n'
            'Also extract slots.public_name when the user provides a public display name.\n'
            'Also extract slots.readiness as ready, not_ready, question, unclear, or empty when applicable.\n'
            'Use per-field confidence from 0 to 1. Keep summaries short and grounded only in the patient text.\n\n'
            f'Current step: {json.dumps(step or {})}\n'
            f'All steps: {json.dumps(steps)}\n'
            f'Existing accepted evidence: {json.dumps(compact_evidence)}\n'
            f'Turn metadata: {json.dumps(turn_meta or {})[:1200]}\n'
            f'Latest user answer: {text}\n'
        )
