"""Deterministic donor-story interview flow helpers.

The LLM should make the interview sound natural, but code owns the
interview contract: intake, story order, follow-up depth, and completion.
"""

from __future__ import annotations

from typing import Any, Callable

from .emotional_support import emotional_support_decision
from .interview_answer_analysis import (
    can_request_deepening,
    extract_patient_name,
    input_guard_decision,
    is_skip_intent,
    no_deepening_decider,
    readiness_decision,
    sufficiency_decision,
    validate_deepening_decision,
)
from .interview_flow_config import (
    FINAL_PHOTOS_PROMPT,
    FOLLOWUP_QUESTIONS,
    GENERATION_REQUIRED_EVIDENCE_GROUPS,
    INTERVIEW_STEPS,
    PROGRESS_LABELS,
    SECTION_TRANSITIONS,
)
from .story_evaluator import structured_answer_decision
from .turn_interpreter import interpret_story_turn


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
        'deepening_count_by_step': {},
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
    base.setdefault('deepening_count_by_step', {})
    base.setdefault('emotional_support_count_by_step', {})
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


def decide_next_task(
    state: dict[str, Any],
    user_input: str = '',
    turn_meta: dict[str, Any] | None = None,
    deepening_decider: Callable[[dict[str, str] | None, str, dict[str, Any]], dict[str, Any]] | None = None,
    answer_evaluator: Callable[[dict[str, str] | None, str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Update state and return the next code-owned task."""
    normalized = normalize_state(state)
    state.clear()
    state.update(normalized)
    if state.get('complete'):
        return _task('already_complete', state, phase='PHOTOS', step=None)

    awaiting = state.get('awaiting')

    if awaiting == 'name':
        name_result = extract_patient_name(user_input)
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
        decision = readiness_decision(user_input)
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

        interpretation = interpret_story_turn(step, state, user_input, awaiting)
        if interpretation['category'] == 'prior_reference':
            state['last_decision'] = {'turn_interpretation': interpretation}
            if interpretation['current_step_has_accepted_evidence']:
                decision = {
                    'sufficient': True,
                    'reason': 'prior_reference_existing_evidence',
                    'matched': interpretation['matched'],
                    'turn_interpretation': interpretation,
                }
                answered_followup_kind = state.get('last_followup_kind') if awaiting == 'followup_answer' else None
                return _advance_or_close(state, decision, answered_followup_kind=answered_followup_kind)

            state['repair_count'] = int(state.get('repair_count') or 0) + 1
            state['phase'] = step['phase'] if step else 'STORY'
            state['awaiting'] = awaiting
            return _task(
                'repair_answer',
                state,
                phase=state['phase'],
                step=step,
                decision={
                    'repair': True,
                    'reason': 'prior_reference_without_evidence',
                    'turn_interpretation': interpretation,
                },
            )

        guard = input_guard_decision(step, user_input, turn_meta)
        if guard['repair']:
            state['last_decision'] = {'input_guard': guard}
            state['repair_count'] = int(state.get('repair_count') or 0) + 1
            state['phase'] = step['phase'] if step else 'STORY'
            state['awaiting'] = awaiting
            return _task('repair_answer', state, phase=state['phase'], step=step, decision=guard)

        decision = structured_answer_decision(step, user_input, sufficiency_decision(step, user_input), answer_evaluator)
        state['last_decision'] = {'sufficiency': decision}
        answered_followup_kind = state.get('last_followup_kind') if awaiting == 'followup_answer' else None
        _record_story_evidence(state, step, user_input, decision, awaiting)

        if awaiting == 'main_answer' and step and int(state.get('followup_count') or 0) < 1:
            emotional = emotional_support_decision(step, user_input, state)
            if emotional.get('should_support'):
                counts = state.setdefault('emotional_support_count_by_step', {})
                counts[step['id']] = int(counts.get(step['id']) or 0) + 1
                state['last_decision'] = {'sufficiency': decision, 'emotional_support': emotional}
                state['followup_count'] = int(state.get('followup_count') or 0) + 1
                state['last_followup_kind'] = 'emotional_support'
                state['awaiting'] = 'followup_answer'
                state['phase'] = step['phase']
                return _task('ask_emotional_support', state, phase=step['phase'], step=step, decision=emotional, sufficiency=decision)

        if (
            awaiting == 'main_answer'
            and step
            and not decision['sufficient']
            and int(state.get('followup_count') or 0) < 1
        ):
            state['followup_count'] = int(state.get('followup_count') or 0) + 1
            state['last_followup_kind'] = 'repair'
            state['awaiting'] = 'followup_answer'
            state['phase'] = step['phase']
            return _task('ask_followup', state, phase=step['phase'], step=step, decision=decision)

        if awaiting == 'main_answer' and step and decision['sufficient'] and can_request_deepening(step, state):
            planner = deepening_decider or no_deepening_decider
            try:
                candidate_deepening = planner(step, user_input, state)
            except Exception as e:
                candidate_deepening = {'should_deepen': False, 'reason': f'planner_error:{type(e).__name__}'}
            deepening = validate_deepening_decision(step, user_input, state, candidate_deepening)
            if deepening['should_deepen']:
                counts = state.setdefault('deepening_count_by_step', {})
                counts[step['id']] = int(counts.get(step['id']) or 0) + 1
                state['last_decision'] = {'sufficiency': decision, 'deepening': deepening}
                state['last_followup_kind'] = 'deepening'
                state['awaiting'] = 'followup_answer'
                state['phase'] = step['phase']
                return _task('ask_deepening', state, phase=step['phase'], step=step, decision=deepening, sufficiency=decision)

        if step and not decision['sufficient']:
            state.setdefault('thin_evidence', {})[step['id']] = decision

        return _advance_or_close(state, decision, answered_followup_kind=answered_followup_kind)

    state['awaiting'] = 'name'
    state['phase'] = 'INTRO'
    return _task('repair_name', state, phase='INTRO', step=None, decision={'reason': 'unknown_state'})


def _recovery_question_text(task: dict[str, Any]) -> str | None:
    step = task.get('step') or {}
    if step.get('id') == 'personal_background':
        return (
            "Can you share something about yourself outside of kidney disease, such as family, work, school, "
            "community, or something you enjoy?"
        )
    return step.get('question')


def deterministic_response(task: dict[str, Any], state: dict[str, Any]) -> str | None:
    task_type = task.get('type')
    name = state.get('patient_name') or ''
    step = task.get('step') or {}
    step_id = step.get('id')
    question = step.get('question')
    if task_type == 'repair_name':
        return "I want to make sure I show your name correctly. What name would you like shown publicly on your donor page?"
    if task_type == 'close_to_photos':
        return FINAL_PHOTOS_PROMPT
    if task_type == 'already_complete':
        return "The story interview is complete. You can continue with the photo step."
    if task_type == 'skip_to_photos':
        return f"No problem, we can skip that. {FINAL_PHOTOS_PROMPT}"
    if task_type == 'skip_then_next' and question:
        return f"No problem, we can skip that. {SECTION_TRANSITIONS.get(step_id, 'Let us continue with the next part of your story')} {question}"
    if task_type == 'ask_readiness' and task.get('decision', {}).get('kind') == 'not_ready':
        return "That's okay. Take your time, and when you're ready, tell me you want to begin."
    if task_type == 'ask_readiness' and task.get('decision', {}).get('kind') == 'unclear':
        return "Before we start the story questions, are you ready to begin?"
    if task_type == 'answer_readiness_question':
        return (
            "This conversation helps create a donor page by collecting your story in your own words. "
            "You can skip anything or correct me at any point. Are you ready to begin?"
        )
    if task_type == 'ask_readiness' and name:
        return (
            f"Thank you, {name}. I'll ask about your life, your kidney journey, and what a transplant could mean for you. "
            "You can skip anything or correct me at any point. Are you ready to begin?"
        )
    if task_type == 'ask_main' and question:
        return f"{SECTION_TRANSITIONS.get(step_id, 'Let us continue with your story')} {question}"
    if task_type == 'recover_generation_evidence':
        recovery_question = _recovery_question_text(task)
        if not recovery_question:
            return None
        return (
            "Before we move to photos, I need one more detail so the donor page can reflect your story. "
            f"{recovery_question}"
        )
    if task_type == 'ask_followup' and step_id:
        followup = (task.get('decision') or {}).get('suggested_followup') or FOLLOWUP_QUESTIONS.get(step_id, question)
        return followup
    if task_type == 'ask_emotional_support':
        support_response = (task.get('decision') or {}).get('response')
        if support_response:
            return support_response
    if task_type == 'ask_deepening':
        deepening_question = (task.get('decision') or {}).get('question')
        if deepening_question:
            return deepening_question
    if task_type == 'repair_answer' and question:
        decision = task.get('decision') or {}
        if decision.get('reason') == 'clarification_request':
            return f"Sure. I was asking about this part of your donor story: {question}"
        if decision.get('reason') == 'empty_or_no_response':
            return f"I did not catch that clearly. Please try again: {question}"
        if decision.get('reason') == 'operational_issue':
            return f"I am sorry, it sounds like the microphone had trouble. Let's try the same question again: {question}"
        if decision.get('reason') == 'prior_reference_without_evidence':
            return f"I may have missed that earlier. Could you share the part you want included for this question? {question}"
        return f"I only caught a little of that. {question}"
    return None


def expected_question_text(task: dict[str, Any]) -> str | None:
    """Return the exact question the backend expects this task to deliver."""
    task_type = task.get('type')
    step = task.get('step') or {}
    if task_type == 'recover_generation_evidence':
        return _recovery_question_text(task)
    if task_type in {'ask_main', 'ack_then_next', 'ask_final', 'repair_answer', 'skip_then_next'}:
        return step.get('question')
    if task_type == 'ask_followup':
        return FOLLOWUP_QUESTIONS.get(step.get('id')) or step.get('question')
    if task_type in {'ask_deepening', 'ask_emotional_support'}:
        return (task.get('decision') or {}).get('question')
    if task_type == 'repair_name':
        return 'What name would you like shown publicly on your donor page?'
    if task_type in {'ask_readiness', 'answer_readiness_question'}:
        return 'Are you ready to begin?'
    return None


def expected_answer_kind(task: dict[str, Any], state: dict[str, Any]) -> str | None:
    task_type = task.get('type')
    if task_type == 'repair_name':
        return 'name'
    if task_type in {'ask_readiness', 'answer_readiness_question'}:
        return 'readiness'
    if task_type in {'ask_main', 'ack_then_next', 'ask_final', 'repair_answer', 'skip_then_next', 'recover_generation_evidence'}:
        return state.get('awaiting') or 'main_answer'
    if task_type in {'ask_followup', 'ask_deepening', 'ask_emotional_support'}:
        return 'followup_answer'
    return None


def build_outgoing_turn_contract(task: dict[str, Any], state: dict[str, Any], response: str, turn_id: str) -> dict[str, Any]:
    """Record what the user actually received and what answer is expected next."""
    question = expected_question_text(task)
    step = task.get('step') or {}
    delivery_validated = bool(question and question in response)
    return {
        'outgoing_turn_id': turn_id,
        'asked_step_id': step.get('id'),
        'asked_question_text': question,
        'expected_answer_kind': expected_answer_kind(task, state),
        'delivered_phase': task.get('phase'),
        'delivery_validated': delivery_validated,
        'task_type': task.get('type'),
    }


def build_runtime_directive(task: dict[str, Any]) -> str:
    """Render a turn-specific instruction block for the LLM."""
    task_type = task.get('type')
    step = task.get('step') or {}
    question = step.get('question', '')
    focus = step.get('focus', '')
    required = step.get('required', '')

    if task_type == 'ask_main':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The patient is ready to begin the donor-story interview.\n'
            f'- Ask this donor-story question in natural conversational wording: "{question}"\n'
            f'- Listen for: {focus}.\n'
            '- Ask only one question.'
        )
    if task_type == 'recover_generation_evidence':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The interview is almost complete, but the donor-page draft needs one missing story detail before photos.\n'
            '- Briefly explain that one more detail is needed before moving to photos.\n'
            f'- Ask this recovery question in natural conversational wording: "{question}"\n'
            f'- Listen for: {focus}.\n'
            '- Ask only one question. Do not move to photos yet.'
        )
    if task_type == 'ask_followup':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The previous answer was too short or missing important story detail.\n'
            '- Briefly acknowledge what the patient said.\n'
            f'- Ask one open follow-up for the same topic: {focus}.\n'
            f'- The answer should help capture: {required}.\n'
            '- Begin with What, How, or Tell me about.\n'
            '- Do not move to a new topic. Ask only one question.'
        )
    if task_type == 'ask_deepening':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The previous answer was usable, but included an important story detail worth understanding more deeply.\n'
            '- Stay on the same topic.\n'
            '- Ask the provided story-deepening follow-up question exactly.\n'
            '- Do not move to a new topic. Ask only one question.'
        )
    if task_type == 'ask_emotional_support':
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- The patient shared emotional distress.\n'
            '- Validate briefly without counseling or medical advice.\n'
            '- Ask the provided optional follow-up question exactly.\n'
            '- Do not ask for unnecessary third-party private details. Ask only one question.'
        )
    if task_type in {'ack_then_next', 'ask_final'}:
        return (
            'RUNTIME TURN DIRECTIVE:\n'
            '- Briefly acknowledge one concrete detail from what the patient just shared or previously clarified.\n'
            '- If the patient says they already mentioned something, acknowledge that and use the earlier context; do not praise it as new detail.\n'
            '- Do not use stock phrases like "That gives this part of your story more depth" or "Thank you for sharing that."\n'
            f'- Then ask this next donor-story question exactly, verbatim, at the end: "{question}"\n'
            f'- Listen for: {focus}.\n'
            '- Ask only one question.'
        )
    return (
        'RUNTIME TURN DIRECTIVE:\n'
        '- Output only patient-facing speech.\n'
        '- Ask only one question.'
    )
