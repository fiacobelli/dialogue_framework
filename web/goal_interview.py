"""LLM-centered interview goal — the whole turn in one place.

The LLM judges whether a story answer needs more detail and writes warm language, but
code assembles the final turn. Section questions are always appended by code on advance;
follow-up turns require an explicit LLM follow-up question. Probing is bounded by
MAX_FOLLOWUPS_PER_SECTION and honored only on eligible steps, so the turn can never stall
or loop. Deterministic guards and state live in interview_state; the 7 sections + config
in interview_flow_config.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any

from goal import Goal
from strings import MSG, BELSTR
from .config import LANGUAGE_NAMES
from .interview_flow_config import (
    FINAL_PHOTOS_PROMPT,
    FOLLOWUP_EXAMPLES,
    INTERVIEW_STEPS,
    MAX_FOLLOWUPS_PER_SECTION,
)
from .interview_state import (
    _advance_step,
    _crisis_detected,
    _missing_recovery_step,
    _record_skipped_step,
    _record_story_evidence,
    build_interview_state,
    current_step,
    input_guard_decision,
    is_skip_intent,
    normalize_answer,
    normalize_state,
)

LOGS_DIR = 'logs'
NAME_QUESTION = 'What name would you like shown publicly on your donor page?'
READINESS_QUESTION = 'Are you ready to begin?'
OBVIOUSLY_VAGUE_ANSWERS = {
    'yes', 'yeah', 'yep', 'it is bad', "it's bad", 'it is hard', "it's hard",
    'it would be better', 'it will be better', "it'll be better", 'it would make it better',
    'it will make it better', "it'll make it better", 'i am a good person', "i'm a good person",
    'i do not know', "i don't know", 'not sure',
}
# Tasks that move to a new section and therefore owe the patient that section's question.
ADVANCE_TASKS = {'ask_main', 'ack_then_next', 'ask_final', 'recover_generation_evidence'}


def _log(session_id: str, entry: str) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, f'interview_{session_id}.txt')
    with open(path, 'a', encoding='utf-8') as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {entry}\n")


# --- Turn contract: directive + JSON parse/validate (the LLM's I/O) ---

def _text(value: Any, limit: int = 1000) -> str:
    return str(value or '').strip()[:limit]


def build_turn_directive(instruction: str, offer_followup: bool = False) -> str:
    """Append the per-turn instruction + output format. Persona/voice rules live in
    prompts/interviewer.txt (the system prompt), not here."""
    if offer_followup:
        return (
            'RUNTIME TURN DIRECTIVE\n'
            f'{instruction.strip()}\n\n'
            'Return ONLY a JSON object (no other text):\n'
            '{\n'
            '  "ack": "one short acknowledgement sentence, no question",\n'
            '  "needs_followup": true or false,\n'
            '  "followup_question": "the one follow-up question if needs_followup is true, otherwise an empty string",\n'
            '  "name": "the patient\'s name if they just gave it, otherwise an empty string"\n'
            '}'
        )
    return (
        'RUNTIME TURN DIRECTIVE\n'
        f'{instruction.strip()}\n\n'
        'Return ONLY a JSON object (no other text):\n'
        '{\n'
        '  "reply": "what you say to the patient, following the voice rules above",\n'
        '  "name": "the patient\'s name if they just gave it, otherwise an empty string"\n'
        '}'
    )


def parse_turn(raw: str) -> dict | None:
    """Extract a JSON object from the model output, tolerating code fences."""
    text = (raw or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def validate_turn(data: dict | None) -> dict:
    """Sanitize the model output into the turn contract fields."""
    data = data if isinstance(data, dict) else {}
    name = re.sub(r'\s+', ' ', _text(data.get('name'), 80)).strip()
    if len(name.split()) > 5:
        name = ''
    reply = _text(data.get('reply'))
    ack = _text(data.get('ack'), 500)
    followup_question = _text(data.get('followup_question'), 500)
    return {
        'reply': reply,
        'ack': ack,
        'name': name,
        'needs_followup': bool(data.get('needs_followup')),
        'followup_question': followup_question,
        'valid': bool(reply or ack or followup_question),
    }


def _probe_contract_valid(turn: dict, can_probe: bool) -> bool:
    if not can_probe:
        return bool(turn.get('valid'))
    if not turn.get('valid'):
        return False
    if turn.get('needs_followup') and not _text(turn.get('followup_question')):
        return False
    return True


# --- State transitions: one question per section, code drives order ---

def has_accepted(state: dict, step_id: str | None) -> bool:
    entries = (state.get('story_evidence') or {}).get(step_id) or []
    if isinstance(entries, dict):
        entries = [entries]
    return any(isinstance(e, dict) and e.get('accepted') for e in entries)


def nonstory_question(awaiting: str) -> str | None:
    if awaiting == 'name':
        return NAME_QUESTION
    return READINESS_QUESTION if awaiting == 'readiness' else None


def _next_question(step_index: int) -> str | None:
    nxt = int(step_index or 0) + 1
    return INTERVIEW_STEPS[nxt]['question'] if nxt < len(INTERVIEW_STEPS) else None


def _post_question(state: dict) -> str:
    """The question we now expect an answer to (fallback reply only)."""
    if state.get('awaiting') == 'name':
        return NAME_QUESTION
    if state.get('awaiting') == 'readiness':
        return READINESS_QUESTION
    step = current_step(state)
    return step['question'] if step else ''


def _join_reply(ack: str, question: str) -> str:
    ack = _text(ack, 500)
    question = _text(question, 500)
    if question and not question.endswith('?'):
        question = f'{question}?'
    return f'{ack} {question}'.strip() if ack else question


def _fallback_followup_question(step: dict | None) -> str:
    return FOLLOWUP_EXAMPLES.get(
        (step or {}).get('id'),
        'Could you tell me a little more, with one specific example?',
    )


def _required_followup_question(step: dict | None, answer: str) -> str:
    if normalize_answer(answer) in OBVIOUSLY_VAGUE_ANSWERS:
        return _fallback_followup_question(step)
    return ''


def _can_probe(state: dict, awaiting: str, step: dict | None, answer: str) -> bool:
    followup_count = int(state.get('followup_count') or 0)
    return (
        awaiting in {'main_answer', 'followup_answer'}
        and step is not None
        and bool(step.get('allow_follow_up'))
        and followup_count < MAX_FOLLOWUPS_PER_SECTION
        and not (awaiting == 'followup_answer' and normalize_answer(answer) in OBVIOUSLY_VAGUE_ANSWERS)
    )


def instruction_for(state: dict, awaiting: str, step: dict | None, can_probe: bool = False) -> str:
    """Build the per-turn instruction telling the LLM what to voice this turn.

    Code owns the section questions: the LLM only acknowledges (and, on probe turns, asks
    its own follow-up). On any advance, emit() appends the canonical next question, so the
    LLM is told NOT to ask the next question itself.
    """
    if awaiting == 'name':
        return ('The patient just told you their name. Greet them warmly by name in one short sentence, '
                'and do NOT ask any question; the system will explain the interview. '
                'Put the name they gave in the "name" field.')
    next_q = _next_question(state.get('step_index') or 0)
    if can_probe and step:
        example = FOLLOWUP_EXAMPLES.get(step.get('id'), step.get('focus', 'what matters most in their story'))
        section_q = step.get('question', 'the current question')
        required = step.get('required', 'a concrete detail relevant to this section')
        probe_rule = (
            'This is the answer to your first follow-up. Set needs_followup to true only if it contains '
            'a useful concrete detail but leaves one important part unclear. Do not ask again if the patient '
            'is unsure, cannot add detail, repeats a vague answer, or has adequately answered. '
            if awaiting == 'followup_answer' else
            'If it is still vague, a yes/no, or generic (for example "I am a good person"), set '
            'needs_followup to true and put one gentle, open follow-up question in followup_question. '
        )
        return (f'The patient just answered: "{section_q}". '
                f'Judge their answer together with relevant details they already shared. '
                f'The answer is adequate when it provides {required}. '
                f'If it is adequate, write only a warm acknowledgement in ack, set needs_followup to false, '
                f'and leave followup_question empty. Do not demand another example just to embellish it. '
                f'{probe_rule}'
                f'Use this topic-specific example as a guide: "{example}"')
    if next_q:
        return ('Warmly acknowledge what the patient just shared in one short sentence that shows you '
                'truly heard them, and do NOT ask any question; the system will ask the next question.')
    return ('Warmly acknowledge what the patient just shared, then thank them sincerely for telling '
            'their story. Do not ask another question.')


def advance_and_maybe_close(state: dict, reply: str) -> tuple[str, str]:
    """Advance the section pointer; recover missing required coverage or close to photos."""
    from .microsite import story_evidence_ready  # lazy: microsite -> session_store would cycle at load

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


def apply_turn(
    state: dict,
    awaiting: str,
    step: dict | None,
    user_input: str,
    turn: dict,
    asked_followup: bool = False,
) -> tuple[str, dict]:
    """Apply the voiced turn to state; return (task_type, decision). One question per section."""
    if awaiting == 'name':
        name = turn['name'] or (user_input or '').strip()[:80]
        state.update(patient_name=name or None,
                     patient_name_status='confirmed' if name else 'missing',
                     patient_name_source='user_explicit', phase='INTRO',
                     awaiting='readiness', step_index=0)
        return 'ask_readiness', {'sufficient': bool(name), 'reason': 'intro_name'}

    if step:
        answer_kind = 'followup_answer' if awaiting == 'followup_answer' else 'main_answer'
        if asked_followup:
            # Still thin: keep probing this section (bounded by MAX_FOLLOWUPS_PER_SECTION via can_probe).
            decision = {'sufficient': False, 'reason': 'needs_elaboration'}
            _record_story_evidence(state, step, user_input, decision, answer_kind)
            state['followup_count'] = int(state.get('followup_count') or 0) + 1
            state['awaiting'] = 'followup_answer'
            state['phase'] = step.get('phase') or 'STORY'
            return 'ask_followup', decision

        reason = 'followup_answered' if awaiting == 'followup_answer' else 'answered'
        _record_story_evidence(state, step, user_input, {'sufficient': True, 'reason': reason}, answer_kind)

    task_type, _reply = advance_and_maybe_close(state, turn['reply'])
    return task_type, {'sufficient': True, 'reason': 'followup_answered' if awaiting == 'followup_answer' else 'answered'}


def emit(msg, info_state, state, previous_state, answered_turn, task_type, decision,
         reply, latency, history, user_input, store_user) -> str:
    """Build the outgoing-turn + analytics contract and persist state. Returns final reply."""
    if task_type == 'close_to_photos':
        reply = FINAL_PHOTOS_PROMPT
        info_state.user.update('interview_phase', 'PHOTOS')

    asked_step = current_step(state) if state.get('awaiting') in {'main_answer', 'followup_answer'} else None

    # Coverage backstop: code owns the section question. On every advance, keep only the
    # model's acknowledgement (drop any question it voiced on its own) and append the
    # canonical next question verbatim, so a chatty model can never skip or substitute it.
    if task_type in ADVANCE_TASKS and asked_step:
        question = asked_step['question']
        norm_reply = (reply or '').strip().lower()
        norm_user = (user_input or '').strip().lower()
        echoed = bool(norm_reply) and (norm_reply in norm_user or norm_user in norm_reply)
        if not reply or echoed:
            reply = question
        else:
            ack = ' '.join(s for s in re.split(r'(?<=[.!?])\s+', reply.strip()) if '?' not in s).strip()
            reply = f"{ack} {question}".strip() if ack else question
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
    if awaiting not in {'name', 'readiness', 'main_answer', 'followup_answer'}:
        awaiting = 'main_answer'
        state['awaiting'], state['phase'] = 'main_answer', 'STORY'
    step = current_step(state)
    _log(session_id, f"USER: {user_input}")

    reply = task_type = None
    decision: dict = {}
    latency = 0
    store_user = bool(user_input) and not turn_meta.get('no_response')
    story_phase = awaiting in {'main_answer', 'followup_answer'}
    can_probe = False

    # ---- deterministic floors (no LLM) ----
    if awaiting == 'readiness':
        normalized = normalize_answer(user_input)
        not_ready = bool(re.search(r"\b(no|wait|unsure)\b|\bnot\b.*\b(ready|sure|start|begin)\b|\bdo not\b|\bdon't\b", normalized))
        ready = bool(re.search(r"\b(yes|yeah|yep|ready|okay|ok|sure|start|begin)\b", normalized))
        if ready and not not_ready:
            state['awaiting'], state['phase'] = 'main_answer', 'STORY'
            reply = current_step(state)['question']
            task_type, decision = 'ask_main', {'sufficient': True, 'reason': 'readiness_confirmed'}
        else:
            reply = "No problem. When you are ready, please say yes."
            task_type, decision = 'wait_for_readiness', {'sufficient': False, 'reason': 'not_ready'}
    elif story_phase and is_skip_intent(user_input, turn_meta):
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

    # ---- one LLM call (plain reply + name hint) ----
    if task_type is None:
        can_probe = _can_probe(state, awaiting, step, user_input)
        prompt = system_prompt.replace('{avatar_name}', avatar) + '\n\n' + build_turn_directive(
            instruction_for(state, awaiting, step, can_probe=can_probe), offer_followup=can_probe)
        if language != 'en':
            prompt += f"\n\nIMPORTANT: Respond entirely in {LANGUAGE_NAMES.get(language, 'English')}."
        llm_history = history + ([{'role': 'user', 'content': user_input}] if store_user else [])
        t0 = time.perf_counter()
        raw = llm.generate(llm_history, prompt, json_mode=True)
        _log(session_id, f"LLM_RAW: {raw[:600]}")
        turn = validate_turn(parse_turn(raw))
        if not _probe_contract_valid(turn, can_probe):
            raw = llm.generate(
                llm_history,
                prompt + '\n\nReturn ONLY the JSON object described above. If needs_followup is true, followup_question must contain one actual question.',
                json_mode=True,
            )
            _log(session_id, f"LLM_RAW_RETRY: {raw[:600]}")
            turn = validate_turn(parse_turn(raw))
        if can_probe and turn.get('valid') and turn.get('needs_followup') and not _text(turn.get('followup_question')):
            turn['followup_question'] = _fallback_followup_question(step)
        required_followup = _required_followup_question(step, user_input) if can_probe and awaiting == 'main_answer' else ''
        if turn.get('valid') and required_followup:
            turn['needs_followup'] = True
            turn['followup_question'] = required_followup
        latency = int((time.perf_counter() - t0) * 1000)

        invalid = not _probe_contract_valid(turn, can_probe)
        if invalid:
            # Model failed even after retry: never lose the answer or stall — record & advance.
            turn = {
                'reply': '',
                'ack': '',
                'name': (user_input or '').strip()[:80] if awaiting == 'name' else '',
                'needs_followup': False,
                'followup_question': '',
            }
        needs_followup = can_probe and bool(turn.get('needs_followup')) and bool(_text(turn.get('followup_question')))
        if can_probe:
            if needs_followup:
                reply = _join_reply(turn.get('ack'), turn.get('followup_question') or _fallback_followup_question(step))
            else:
                reply = _text(turn.get('ack')) or _text(turn.get('reply'))
        else:
            reply = turn.get('reply') or turn.get('ack') or ''
        task_type, decision = apply_turn(state, awaiting, step, user_input, turn, asked_followup=needs_followup)
        if awaiting == 'name':
            name = state.get('patient_name') or 'there'
            reply = (f"Thank you, {name}. We are about to begin the interview. "
                     f"I will ask you {len(INTERVIEW_STEPS)} main questions about your story. {READINESS_QUESTION}")
        if invalid:
            decision = {'sufficient': True, 'reason': 'invalid_llm_json'}
        if not reply:
            reply = _post_question(state)
        _log(session_id, f"TURN: task={task_type} awaiting={state.get('awaiting')} step={state.get('step_index')} "
                         f"can_probe={can_probe} needs_followup={needs_followup} "
                         f"followup_question={bool(_text(turn.get('followup_question')))}")

    final_reply = emit(msg, info_state, state, previous_state, answered_turn, task_type,
                       decision, reply, latency, history, user_input, store_user)
    _log(session_id, f"OUTGOING: {final_reply}")


# --- Framework integration ---

class InterviewGoal(Goal):
    def __init__(self, llm_provider, system_prompt: str):
        self.llm = llm_provider
        self.system_prompt = system_prompt

    def is_complete(self, info_state) -> bool:
        return info_state.user.query('interview_phase') == 'PHOTOS'

    def execute_goal(self, msg, info_state):
        run_turn(msg, info_state, self.llm, self.system_prompt)

    def get_next_prompt(self, msg, info_state) -> dict:
        msg[MSG.PROMPT] = msg.get(MSG.RESPONSE, '')
        return msg


class InterviewGoalManager:
    def __init__(self, llm_provider, system_prompt: str):
        self.goal = InterviewGoal(llm_provider, system_prompt)
        self.system_prompt = system_prompt

    def update(self, msg, info_state):
        if self.goal.is_complete(info_state):
            info_state.bel.add(BELSTR.DONE, True)
            return
        self.goal.execute_goal(msg, info_state)
        self.goal.get_next_prompt(msg, info_state)

    def get_opening(
        self,
        info_state,
        lang: str = 'en',
        avatar_name: str = 'Assistant',
        is_returning: bool = False,
    ) -> str:
        """Return a deterministic opening greeting and seed the interview state."""
        state = build_interview_state()
        if is_returning:
            opening = (
                f"Welcome back, I'm {avatar_name}. "
                "I'm glad you're here again. "
                "Let's continue telling your story together. What name would you like shown publicly on your donor page?"
            )
        else:
            opening = (
                f"Hi there, I'm {avatar_name}. "
                "I'm here to help create a donor page by learning your story in your own words. "
                "You can skip anything or correct me at any point. "
                "What name would you like shown publicly on your donor page? You can give your full name or just your first name."
            )

        state['current_outgoing_turn'] = {
            'outgoing_turn_id': str(uuid.uuid4()),
            'asked_step_id': None,
            'asked_question_text': 'What name would you like shown publicly on your donor page?',
            'expected_answer_kind': 'name',
            'delivered_phase': 'WELCOME',
            'delivery_validated': True,
            'task_type': 'opening',
        }
        info_state.user.update('interview_state', state)
        info_state.user.update('interview_phase', 'WELCOME')

        history = [{"role": "assistant", "content": opening}]
        info_state.user.update('conversation_history', history)

        return opening
