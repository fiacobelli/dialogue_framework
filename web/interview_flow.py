"""Deterministic donor-story interview flow helpers.

The LLM should make the interview sound natural, but code owns the
interview contract: intake, story order, follow-up depth, and completion.
"""

from __future__ import annotations

from typing import Any

from .interview_decision import (
    classify_story_answer,
    input_guard_decision,
    is_skip_intent,
)
from .interview_prompts import (
    build_outgoing_turn_contract,
    build_runtime_directive,
    deterministic_response,
    expected_answer_kind,
    expected_question_text,
)
from .interview_flow_config import (
    FINAL_PHOTOS_PROMPT,
    GENERATION_REQUIRED_EVIDENCE_GROUPS,
    INTERVIEW_STEPS,
    PROGRESS_LABELS,
)


def build_interview_state() -> dict[str, Any]:
    """Initial state stored in info_state.user."""
    return {
        'version': 2,
        'step_index': 0,
        'phase': 'INTRO',
        'awaiting': 'name',
        'followup_count': 0,
        'repair_count': 0,
        'last_task': 'opening',
        'last_step_id': None,
        'complete': False,
        'story_evidence': {},
        'skipped_steps': {},
        'thin_evidence': {},
        'last_followup_kind': None,
        'patient_name': None,
        'patient_name_status': 'missing',
        'patient_name_source': None,
        'last_decision': None,
    }


def normalize_state(state: dict[str, Any] | None) -> dict[str, Any]:
    """Return a v2-compatible state, preserving safe values from older states."""
    base = build_interview_state()
    if not isinstance(state, dict):
        return base

    base.update(state)
    base['version'] = 2
    if base.get('awaiting') == 'story_answer':
        base['awaiting'] = 'main_answer'
    if base.get('phase') in {'WELCOME', 'BEFORE', 'DURING', 'HOPE'}:
        base['phase'] = 'INTRO' if base.get('awaiting') == 'name' else 'STORY'
    base.setdefault('followup_count', 0)
    base.setdefault('repair_count', 0)
    base.setdefault('story_evidence', {})
    base.setdefault('skipped_steps', {})
    base.setdefault('thin_evidence', {})
    base.setdefault('last_followup_kind', None)
    base.setdefault('patient_name_status', 'missing')
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
    state['repair_count'] = 0
    state['last_followup_kind'] = None
    return current_step(state)


def _clean_text(value: Any) -> str:
    return str(value or '').strip()


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
) -> None:
    if not step:
        return
    entry = {
        'answer': user_input,
        'sufficiency': decision,
        'followup_count': state.get('followup_count', 0),
        'answer_kind': answer_kind,
        'followup_kind': state.get('last_followup_kind') if answer_kind == 'followup_answer' else None,
        'accepted': bool(decision.get('sufficient')),
    }
    evidence = state.setdefault('story_evidence', {})
    step_entries = evidence.setdefault(step['id'], [])
    if isinstance(step_entries, list):
        step_entries.append(entry)
    else:
        evidence[step['id']] = [step_entries, entry]


def _step_has_accepted_evidence(state: dict[str, Any], step_id: str | None) -> bool:
    if not step_id:
        return False
    entries = (state.get('story_evidence') or {}).get(step_id) or []
    if isinstance(entries, dict):
        entries = [entries]
    return any(isinstance(entry, dict) and entry.get('accepted') for entry in entries)


def _step_has_future_evidence(state: dict[str, Any], step_id: str | None) -> bool:
    if not step_id:
        return False
    entries = (state.get('story_evidence') or {}).get(step_id) or []
    if isinstance(entries, dict):
        entries = [entries]
    return any(
        isinstance(entry, dict)
        and entry.get('accepted')
        and entry.get('answer_kind') == 'future_answer'
        for entry in entries
    )


def _record_future_evidence_from_nlu(
    state: dict[str, Any],
    turn_meta: dict[str, Any] | None,
    user_input: str,
    current_step_id: str | None,
) -> None:
    frame = (turn_meta or {}).get('evidence_interpretation_shadow') or {}
    for item in frame.get('future_evidence') or []:
        step_id = item.get('step_id')
        if not step_id or step_id == current_step_id or _step_has_accepted_evidence(state, step_id):
            continue
        try:
            confidence = float(item.get('confidence') or 0)
        except (TypeError, ValueError):
            confidence = 0
        if item.get('status') not in {'sufficient', 'explicit_none'} or confidence < 0.65:
            continue
        step = next((candidate for candidate in INTERVIEW_STEPS if candidate.get('id') == step_id), None)
        if not step:
            continue
        _record_story_evidence(
            state,
            step,
            user_input,
            {
                'sufficient': True,
                'reason': 'semantic_future_evidence',
                'matched': item.get('summary'),
                'semantic_confidence': confidence,
            },
            'future_answer',
        )


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


def _advance_or_close(state: dict[str, Any], decision: dict[str, Any], *, default_task_type: str = 'ack_then_next',
                      close_task_type: str = 'close_to_photos', answered_followup_kind: str | None = None,
                      **extra: Any) -> dict[str, Any]:
    if state.get('recovery_to_photos'):
        return _recover_or_close_to_photos(state, decision, close_task_type=close_task_type, **extra)

    next_step = _advance_step(state)
    while next_step and next_step.get('id') != 'final_details' and _step_has_future_evidence(state, next_step.get('id')):
        next_step = _advance_step(state)
    if next_step:
        state['awaiting'] = 'main_answer'
        state['phase'] = next_step['phase']
        task_type = 'ask_final' if default_task_type == 'ack_then_next' and next_step['id'] == 'final_details' else default_task_type
        return _task(task_type, state, phase=next_step['phase'], step=next_step, decision=decision, answered_followup_kind=answered_followup_kind, **extra)
    return _recover_or_close_to_photos(state, decision, close_task_type=close_task_type, **extra)


def _recover_or_close_to_photos(
    state: dict[str, Any],
    decision: dict[str, Any],
    *,
    close_task_type: str = 'close_to_photos',
    **extra: Any,
) -> dict[str, Any]:
    missing_label, recovery_step = _missing_recovery_step(state)
    if recovery_step:
        index = _step_index_for_id(recovery_step['id'])
        if index is not None:
            state['step_index'] = index
        state['awaiting'] = 'main_answer'
        state['phase'] = recovery_step['phase']
        state['complete'] = False
        state['followup_count'] = 0
        state['repair_count'] = 0
        state['last_followup_kind'] = None
        state['recovery_to_photos'] = True
        return _task(
            'recover_generation_evidence',
            state,
            phase=recovery_step['phase'],
            step=recovery_step,
            decision=decision,
            missing_story_section=missing_label,
            **extra,
        )
    state['awaiting'] = 'photos'
    state['phase'] = 'PHOTOS'
    state['complete'] = True
    state.pop('recovery_to_photos', None)
    return _task(close_task_type, state, phase='PHOTOS', step=None, decision=decision, **extra)


def _task(task_type: str, state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    phase = extra.pop('phase', state.get('phase', 'INTRO'))
    step = extra.get('step', current_step(state))
    state['last_task'] = task_type
    state['last_step_id'] = step.get('id') if step else None
    return {'type': task_type, 'phase': phase, 'step': step, **extra}


def _name_from_nlu(turn_meta: dict[str, Any] | None) -> dict[str, Any] | None:
    frame = (turn_meta or {}).get('evidence_interpretation_shadow') or {}
    slots = frame.get('slots') if isinstance(frame.get('slots'), dict) else {}
    name = _clean_text(slots.get('public_name'))
    try:
        confidence = float(slots.get('public_name_confidence') or 0)
    except (TypeError, ValueError):
        confidence = 0
    if name and confidence >= 0.65:
        return {'name': name, 'status': 'captured', 'reason': 'nlu_slot', 'confidence': confidence}
    return None


def _readiness_from_nlu(turn_meta: dict[str, Any] | None) -> dict[str, Any] | None:
    frame = (turn_meta or {}).get('evidence_interpretation_shadow') or {}
    slots = frame.get('slots') if isinstance(frame.get('slots'), dict) else {}
    readiness = _clean_text(slots.get('readiness'))
    try:
        confidence = float(slots.get('readiness_confidence') or 0)
    except (TypeError, ValueError):
        confidence = 0
    if confidence < 0.65 or readiness not in {'ready', 'not_ready', 'question'}:
        return None
    return {
        'ready': readiness == 'ready',
        'kind': readiness,
        'matched': 'nlu_slot',
        'confidence': confidence,
    }


def decide_next_task(
    state: dict[str, Any],
    user_input: str = '',
    turn_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update state and return the next code-owned task."""
    normalized = normalize_state(state)
    state.clear()
    state.update(normalized)
    if state.get('complete'):
        return _task('already_complete', state, phase='PHOTOS', step=None)

    awaiting = state.get('awaiting')

    if awaiting == 'name':
        name_result = _name_from_nlu(turn_meta) or {
            'name': None,
            'status': 'missing',
            'reason': 'semantic_nlu_required',
        }
        state['last_decision'] = {'name': name_result}
        if not name_result['name']:
            state['phase'] = 'INTRO'
            state['awaiting'] = 'name'
            return _task('repair_name', state, phase='INTRO', step=None, decision=name_result)
        state['patient_name'] = name_result['name']
        state['patient_name_status'] = 'confirmed'
        state['patient_name_source'] = 'user_explicit'
        state['phase'] = 'INTRO'
        state['awaiting'] = 'readiness'
        return _task('ask_readiness', state, phase='INTRO', step=None, decision=name_result)

    if awaiting == 'readiness':
        decision = _readiness_from_nlu(turn_meta) or {
            'ready': False,
            'kind': 'unclear',
            'matched': None,
            'reason': 'semantic_nlu_required',
        }
        state['last_decision'] = {'readiness': decision}
        if decision['ready']:
            state['phase'] = 'STORY'
            state['awaiting'] = 'main_answer'
            state['followup_count'] = 0
            step = current_step(state)
            return _task('ask_main', state, phase=step['phase'], step=step, decision=decision)
        if decision['kind'] == 'question':
            state['phase'] = 'INTRO'
            state['awaiting'] = 'readiness'
            return _task('answer_readiness_question', state, phase='INTRO', step=None, decision=decision)
        state['phase'] = 'INTRO'
        state['awaiting'] = 'readiness'
        return _task('ask_readiness', state, phase='INTRO', step=None, decision=decision)

    if awaiting in {'main_answer', 'followup_answer'}:
        step = current_step(state)
        if step and is_skip_intent(user_input, turn_meta):
            _record_skipped_step(state, step, user_input, awaiting)
            decision = {'skipped': True, 'step_id': step['id']}
            state['last_decision'] = {'skip': decision}
            return _advance_or_close(
                state, decision, default_task_type='skip_then_next', close_task_type='skip_to_photos', skipped_step=step
            )

        decision = classify_story_answer(step, user_input, state, turn_meta)
        state['last_decision'] = {'sufficiency': decision}
        answered_followup_kind = state.get('last_followup_kind') if awaiting == 'followup_answer' else None

        if decision['action'] == 'safety_response':
            state['repair_count'] = int(state.get('repair_count') or 0) + 1
            state['phase'] = step['phase'] if step else 'STORY'
            state['awaiting'] = awaiting
            return _task('safety_response', state, phase=state['phase'], step=step, decision=decision)

        guard_reasons = {
            'empty_or_no_response',
            'semantic_operational_issue',
            'semantic_clarification',
            'semantic_non_answer',
            'semantic_unclear',
            'low_confidence_fragment',
            'semantic_nlu_required',
        }
        if decision['action'] == 'ask_followup' and decision.get('reason') in guard_reasons:
            state['repair_count'] = int(state.get('repair_count') or 0) + 1
            state['phase'] = step['phase'] if step else 'STORY'
            state['awaiting'] = awaiting
            return _task('repair_answer', state, phase=state['phase'], step=step, decision=decision)

        if (
            decision['action'] == 'ask_followup'
            and step
            and awaiting == 'main_answer'
            and int(state.get('followup_count') or 0) < 1
        ):
            state['followup_count'] = int(state.get('followup_count') or 0) + 1
            state['last_followup_kind'] = 'repair'
            state['awaiting'] = 'followup_answer'
            state['phase'] = step['phase']
            return _task('ask_followup', state, phase=step['phase'], step=step, decision=decision)

        if decision.get('record_current_answer'):
            _record_story_evidence(state, step, user_input, decision, awaiting)
        _record_future_evidence_from_nlu(state, turn_meta, user_input, step.get('id') if step else None)

        if step and not decision['sufficient']:
            state.setdefault('thin_evidence', {})[step['id']] = decision

        return _advance_or_close(state, decision, answered_followup_kind=answered_followup_kind)

    state['awaiting'] = 'name'
    state['phase'] = 'INTRO'
    return _task('repair_name', state, phase='INTRO', step=None, decision={'reason': 'unknown_state'})
