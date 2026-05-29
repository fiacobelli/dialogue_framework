"""State transitions + analytics/outgoing-turn contract for the LLM turn.

Code drives section order; the LLM only voices each turn. `deepen` is an advisory
follow-up hint, capped at one per section and defaulting to advance, so the flow
can never stall. Reuses interview_flow recorders so story_evidence shape cannot
drift from what microsite.py consumes.
"""

from __future__ import annotations

import uuid

from strings import MSG
from .interview_flow import (
    _advance_step,
    _missing_recovery_step,
    _record_story_evidence,
    current_step,
)
from .interview_flow_config import FINAL_PHOTOS_PROMPT, INTERVIEW_STEPS
from .microsite import story_evidence_ready

NAME_QUESTION = 'What name would you like shown publicly on your donor page?'
# Tasks that move to a new section and therefore owe the patient that section's question.
ADVANCE_TASKS = {'ask_main', 'ack_then_next', 'ask_final', 'recover_generation_evidence'}


def has_accepted(state: dict, step_id: str | None) -> bool:
    entries = (state.get('story_evidence') or {}).get(step_id) or []
    if isinstance(entries, dict):
        entries = [entries]
    return any(isinstance(e, dict) and e.get('accepted') for e in entries)


def nonstory_question(awaiting: str) -> str | None:
    return NAME_QUESTION if awaiting == 'name' else None


def _next_question(step_index: int) -> str | None:
    nxt = int(step_index or 0) + 1
    return INTERVIEW_STEPS[nxt]['question'] if nxt < len(INTERVIEW_STEPS) else None


def instruction_for(state: dict, awaiting: str, step: dict | None) -> str:
    """Build the per-turn instruction telling the LLM what to voice this turn."""
    if awaiting == 'name':
        return (f'The patient just told you their name. Greet them warmly and ask this first '
                f'question naturally: "{INTERVIEW_STEPS[0]["question"]}". '
                f'Put the name they gave in the "name" field.')
    next_q = _next_question(state.get('step_index') or 0)
    if next_q:
        return (f'Warmly acknowledge what the patient just shared in one short sentence that shows you '
                f'truly heard them, then ask this next question naturally: "{next_q}".')
    return ('Warmly acknowledge what the patient just shared, then thank them sincerely for telling '
            'their story. Do not ask another question.')


def advance_and_maybe_close(state: dict, reply: str) -> tuple[str, str]:
    """Advance the section pointer; recover missing required coverage or close to photos."""
    nxt = _advance_step(state)
    while nxt and nxt['id'] != 'final_details' and has_accepted(state, nxt['id']):
        nxt = _advance_step(state)
    if nxt:
        state['awaiting'] = 'main_answer'
        state['phase'] = nxt['phase']
        return ('ask_final' if nxt['id'] == 'final_details' else 'ack_then_next'), reply
    if not story_evidence_ready(state)['ready']:
        _label, recovery = _missing_recovery_step(state)
        if recovery:
            state['step_index'] = next(i for i, s in enumerate(INTERVIEW_STEPS) if s['id'] == recovery['id'])
            state['awaiting'] = 'main_answer'
            state['phase'] = recovery['phase']
            return 'recover_generation_evidence', reply
    state['awaiting'] = 'photos'
    state['phase'] = 'PHOTOS'
    state['complete'] = True
    return 'close_to_photos', FINAL_PHOTOS_PROMPT


def apply_turn(state: dict, awaiting: str, step: dict | None, user_input: str, turn: dict) -> tuple[str, dict]:
    """Apply the voiced turn to state; return (task_type, decision). One question per section."""
    if awaiting == 'name':
        name = turn['name'] or (user_input or '').strip()[:80]
        state.update(patient_name=name or None,
                     patient_name_status='confirmed' if name else 'missing',
                     patient_name_source='user_explicit', phase='STORY',
                     awaiting='main_answer', step_index=0)
        return 'ask_main', {'sufficient': bool(name), 'reason': 'intro_name'}

    if step:
        _record_story_evidence(state, step, user_input, {'sufficient': True, 'reason': 'answered'}, 'main_answer')

    task_type, _reply = advance_and_maybe_close(state, turn['reply'])
    return task_type, {'sufficient': True, 'reason': 'answered'}


def emit(msg, info_state, state, previous_state, answered_turn, task_type, decision,
         reply, latency, history, user_input, store_user) -> str:
    """Build the outgoing-turn + analytics contract and persist state. Returns final reply."""
    if task_type == 'close_to_photos':
        reply = FINAL_PHOTOS_PROMPT
        info_state.user.update('interview_phase', 'PHOTOS')

    asked_step = current_step(state) if state.get('awaiting') in {'main_answer', 'followup_answer'} else None

    # Guarantee the section's question is actually asked when advancing. Weak models
    # sometimes only acknowledge, or echo the patient verbatim; without this, the pointer
    # advances but the patient was never asked and the next utterance is mis-recorded.
    # A natural question the LLM did ask is left untouched.
    if task_type in ADVANCE_TASKS and asked_step:
        question = asked_step['question']
        norm_reply = (reply or '').strip().lower()
        norm_user = (user_input or '').strip().lower()
        echoed = bool(norm_reply) and (norm_reply in norm_user or norm_user in norm_reply)
        if not reply or echoed:
            reply = question
        elif '?' not in reply:
            reply = f"{reply} {question}"
    state['last_task'] = task_type
    state['last_step_id'] = asked_step['id'] if asked_step else state.get('last_step_id')
    state['last_decision'] = decision
    outgoing = {
        'outgoing_turn_id': str(uuid.uuid4()),
        'asked_step_id': asked_step['id'] if asked_step else None,
        'asked_question_text': asked_step['question'] if asked_step else nonstory_question(state.get('awaiting')),
        'expected_answer_kind': state.get('awaiting'),
        'delivered_phase': state.get('phase'),
        'delivery_validated': True,
        'task_type': task_type,
    }
    state['current_outgoing_turn'] = outgoing

    if store_user:
        history.append({'role': 'user', 'content': user_input})
    history.append({'role': 'assistant', 'content': reply})
    info_state.user.update('conversation_history', history)
    info_state.user.update('interview_state', state)
    info_state.user.update('interview_phase', state.get('phase'))
    info_state.user.update('patient_name', state.get('patient_name'))
    info_state.user.update('patient_name_status', state.get('patient_name_status'))
    info_state.user.update('patient_name_source', state.get('patient_name_source'))

    msg['interview_task'] = {'type': task_type, 'phase': state.get('phase'),
                             'step': asked_step or {}, 'decision': decision}
    msg['interview_context'] = {
        'answered_awaiting': answered_turn.get('expected_answer_kind') or previous_state.get('awaiting'),
        'answered_step_id': answered_turn.get('asked_step_id') or previous_state.get('last_step_id'),
        'answered_question_text': answered_turn.get('asked_question_text'),
        'answered_outgoing_turn_id': answered_turn.get('outgoing_turn_id'),
        'answered_delivery_validated': answered_turn.get('delivery_validated'),
        'answered_phase': answered_turn.get('delivered_phase'),
        'outgoing_turn': outgoing,
    }
    msg['llm_latency_ms'] = latency
    msg[MSG.RESPONSE] = reply
    return reply
