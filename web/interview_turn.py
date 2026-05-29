"""LLM-centered interview turn (one call per turn).

The LLM only voices the turn (plain reply + advisory hints). Code owns section
order, coverage, safety, skip, no-response, completion, and the analytics
contract. Modeled on the screening tool: nothing in the flow waits on an
LLM-produced flag, so the turn can never stall.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

from strings import MSG
from .config import LANGUAGE_NAMES
from .interview_contract import build_turn_directive, parse_turn, validate_turn
from .interview_decision import _crisis_detected, input_guard_decision, is_skip_intent
from .interview_flow import (
    _record_skipped_step,
    build_interview_state,
    current_step,
    normalize_state,
)
from .interview_turn_apply import (
    NAME_QUESTION,
    advance_and_maybe_close,
    apply_turn,
    emit,
    instruction_for,
)

LOGS_DIR = 'logs'


def _log(session_id: str, entry: str) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, f'interview_{session_id}.txt')
    with open(path, 'a', encoding='utf-8') as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {entry}\n")


def _post_question(state: dict) -> str:
    """The question we now expect an answer to (used only as a fallback reply)."""
    if state.get('awaiting') == 'name':
        return NAME_QUESTION
    step = current_step(state)
    return step['question'] if step else ''


def run_turn(msg: dict, info_state, llm, system_prompt: str) -> None:
    """Process one interview turn end to end and populate msg for routes_api."""
    history = info_state.user.query('conversation_history') or []
    user_input = msg.get(MSG.ORIG_TEXT, '')
    turn_meta = msg.get('turn_meta') or {}
    language = info_state.user.query('language') or 'en'
    session_id = info_state.user.query('session_id') or 'unknown'
    avatar = (info_state.user.query('avatar_profile') or {}).get('name', 'Assistant')

    state = normalize_state(info_state.user.query('interview_state') or build_interview_state())
    previous_state = dict(state)
    answered_turn = previous_state.get('current_outgoing_turn') or {}
    awaiting = state.get('awaiting')
    if awaiting not in {'name', 'main_answer'}:
        awaiting = 'main_answer'  # coerce legacy states (e.g. 'readiness'/'followup_answer') into the story
        state['awaiting'], state['phase'] = 'main_answer', 'STORY'
    step = current_step(state)
    _log(session_id, f"USER: {user_input}")

    reply = task_type = None
    decision: dict = {}
    latency = 0
    store_user = bool(user_input) and not turn_meta.get('no_response')
    story_phase = awaiting == 'main_answer'

    # ---- deterministic floors (no LLM) ----
    if story_phase and is_skip_intent(user_input, turn_meta):
        _record_skipped_step(state, step, user_input, awaiting)
        decision = {'sufficient': True, 'reason': 'skip_requested', 'skipped': True}
        task_type, _ = advance_and_maybe_close(state, '')
        nxt = current_step(state)
        reply = '' if task_type == 'close_to_photos' else (
            f"No problem, we can skip that. {nxt['question']}" if nxt else "No problem, we can skip that.")
        store_user = False
    elif story_phase and _crisis_detected(user_input, turn_meta):
        reply = ("I'm really sorry you're feeling this. This tool cannot provide crisis support. "
                 "If you might hurt yourself, please call or text 988 now, or tell someone near you. "
                 "Would you like to pause here?")
        task_type, decision, store_user = 'safety_response', {'sufficient': False, 'reason': 'safety_crisis'}, False
        state['awaiting'], state['phase'] = awaiting, (step['phase'] if step else 'STORY')
    elif story_phase and input_guard_decision(step, user_input, turn_meta)['repair']:
        reply = f"I did not catch that clearly. {step['question'] if step else ''}".strip()
        task_type, decision, store_user = 'repair_answer', {'sufficient': False, 'reason': 'empty_or_no_response'}, False
        state['awaiting'], state['phase'] = awaiting, (step['phase'] if step else 'STORY')

    # ---- one LLM call (plain reply + advisory hints) ----
    if task_type is None:
        prompt = system_prompt.replace('{avatar_name}', avatar) + '\n\n' + build_turn_directive(
            instruction_for(state, awaiting, step))
        if language != 'en':
            prompt += f"\n\nIMPORTANT: Respond entirely in {LANGUAGE_NAMES.get(language, 'English')}."
        llm_history = history + ([{'role': 'user', 'content': user_input}] if store_user else [])
        t0 = time.perf_counter()
        raw = llm.generate(llm_history, prompt, json_mode=True)
        _log(session_id, f"LLM_RAW: {raw[:600]}")
        turn = validate_turn(parse_turn(raw))
        if not turn['valid']:
            raw = llm.generate(llm_history, prompt + '\n\nReturn ONLY the JSON object described above.', json_mode=True)
            _log(session_id, f"LLM_RAW_RETRY: {raw[:600]}")
            turn = validate_turn(parse_turn(raw))
        latency = int((time.perf_counter() - t0) * 1000)

        invalid = not turn['valid']
        if invalid:
            # Model failed even after retry: never lose the answer or stall — record & advance.
            turn = {'reply': '', 'name': (user_input or '').strip()[:80] if awaiting == 'name' else ''}
        reply = turn['reply']
        task_type, decision = apply_turn(state, awaiting, step, user_input, turn)
        if invalid:
            decision = {'sufficient': True, 'reason': 'invalid_llm_json'}
        if not reply:
            reply = _post_question(state)
        _log(session_id, f"TURN: task={task_type} awaiting={state.get('awaiting')} step={state.get('step_index')}")

    final_reply = emit(msg, info_state, state, previous_state, answered_turn, task_type,
                       decision, reply, latency, history, user_input, store_user)
    _log(session_id, f"OUTGOING: {final_reply}")
