"""Interview goal - LLM-driven interview using system prompt."""
import os
import time
import uuid
from datetime import datetime
from goal import Goal
from strings import MSG, BELSTR
from .config import INTERVIEW_EVIDENCE_SHADOW, LANGUAGE_NAMES
from .evidence_interpreter import EvidenceInterpreter
from .interview_flow import (
    build_interview_state,
    build_outgoing_turn_contract,
    build_runtime_directive,
    current_step,
    decide_next_task,
    deterministic_response,
    normalize_state,
)

LOGS_DIR = 'logs'


def log_interview(session_id: str, entry: str):
    """Append a log entry for debugging interviews."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    filepath = os.path.join(LOGS_DIR, f'interview_{session_id}.txt')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {entry}\n")


class InterviewGoal(Goal):
    def __init__(self, llm_provider, system_prompt: str):
        self.llm = llm_provider
        self.system_prompt = system_prompt

    def is_complete(self, info_state) -> bool:
        return info_state.user.query('interview_phase') == 'PHOTOS'

    def execute_goal(self, msg, info_state):
        history = info_state.user.query('conversation_history') or []
        user_input = msg.get(MSG.ORIG_TEXT, '')
        language = info_state.user.query('language') or 'en'
        session_id = info_state.user.query('session_id') or 'unknown'
        state = normalize_state(info_state.user.query('interview_state') or build_interview_state())
        previous_state = dict(state)
        answered_turn = previous_state.get('current_outgoing_turn') or {}

        log_interview(session_id, f"USER: {user_input}")

        avatar_profile = info_state.user.query('avatar_profile') or {}
        avatar_name = avatar_profile.get('name', 'Assistant')
        self._attach_shadow_evidence_frame(msg, state, history, session_id)
        task = decide_next_task(
            state,
            user_input,
            msg.get('turn_meta'),
        )
        decision = task.get('decision') or {}
        should_store_user = bool(user_input) and not msg.get('turn_meta', {}).get('no_response')
        if task.get('type') == 'repair_answer' and decision.get('reason') in {
            'empty_or_no_response',
            'operational_issue',
            'clarification_request',
        }:
            should_store_user = False
        if task.get('type') in {'skip_then_next', 'skip_to_photos'}:
            should_store_user = False
        if should_store_user:
            history.append({"role": "user", "content": user_input})
            info_state.user.update('conversation_history', history)
        answered_awaiting = answered_turn.get('expected_answer_kind') or previous_state.get('awaiting')
        answered_step_id = answered_turn.get('asked_step_id') or previous_state.get('last_step_id') or state.get('last_step_id')
        log_interview(
            session_id,
            f"FLOW_TASK: {task['type']} phase={task['phase']} "
            f"step={state.get('last_step_id')} previous={previous_state} decision={state.get('last_decision')}"
        )

        response = deterministic_response(task, state)
        if response is None:
            prompt = self._build_prompt(avatar_name, language, build_runtime_directive(task))
            if language != 'en':
                lang_name = LANGUAGE_NAMES.get(language, 'English')
                prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."
            t0 = time.perf_counter()
            response = self.llm.generate(history, prompt)
            llm_latency_ms = int((time.perf_counter() - t0) * 1000)
        else:
            llm_latency_ms = 0
        outgoing_turn = build_outgoing_turn_contract(
            task,
            state,
            response,
            str(uuid.uuid4()),
        )
        state['current_outgoing_turn'] = outgoing_turn
        log_interview(session_id, f"LLM: {response}")
        log_interview(session_id, f"OUTGOING_TURN: {outgoing_turn}")

        # Code owns completion. Phrase matching must never force an early photo transition.
        is_ending = task['type'] in {'close_to_photos', 'skip_to_photos'}
        log_interview(session_id, f"_is_goodbye check: {is_ending}")

        if is_ending:
            info_state.user.update('interview_phase', 'PHOTOS')
            state['phase'] = 'PHOTOS'
            state['complete'] = True
            state['current_outgoing_turn'] = outgoing_turn
            info_state.user.update('interview_state', state)
            log_interview(session_id, "PHASE CHANGED TO: PHOTOS")

        info_state.user.update('interview_state', state)
        info_state.user.update('interview_phase', state.get('phase') or task['phase'])
        info_state.user.update('patient_name', state.get('patient_name'))
        info_state.user.update('patient_name_status', state.get('patient_name_status'))
        info_state.user.update('patient_name_source', state.get('patient_name_source'))

        history.append({"role": "assistant", "content": response})
        info_state.user.update('conversation_history', history)
        msg['interview_task'] = task
        msg['interview_context'] = {
            'answered_awaiting': answered_awaiting,
            'answered_step_id': answered_step_id,
            'answered_question_text': answered_turn.get('asked_question_text'),
            'answered_outgoing_turn_id': answered_turn.get('outgoing_turn_id'),
            'answered_delivery_validated': answered_turn.get('delivery_validated'),
            'answered_phase': answered_turn.get('delivered_phase'),
            'outgoing_turn': outgoing_turn,
        }
        msg['llm_latency_ms'] = llm_latency_ms
        msg[MSG.RESPONSE] = response

    def _attach_shadow_evidence_frame(self, msg, state: dict, history: list, session_id: str) -> None:
        """Run semantic NLU in shadow mode without changing behavior."""
        if not INTERVIEW_EVIDENCE_SHADOW:
            return
        if state.get('awaiting') not in {'main_answer', 'followup_answer'}:
            return
        user_input = msg.get(MSG.ORIG_TEXT, '')
        if not user_input:
            return
        frame = EvidenceInterpreter(self.llm).interpret(
            user_input,
            current_step(state),
            state,
            msg.get('turn_meta') or {},
            history,
        )
        msg['evidence_interpretation_shadow'] = frame
        turn_meta = dict(msg.get('turn_meta') or {})
        turn_meta['evidence_interpretation_shadow'] = frame
        msg['turn_meta'] = turn_meta
        log_interview(session_id, f"EVIDENCE_SHADOW: {frame}")

    def _is_goodbye(self, text: str) -> bool:
        """Check if the response signals end of interview."""
        text_lower = text.lower()
        # Match specific ending phrases, not broad keywords like "microsite"
        # which can appear in questions (e.g., "what tone for your microsite?")
        end_phrases = [
            'thank you for sharing your story',
            'let me put together your page',
            'please upload 3 photos',
        ]
        return any(phrase in text_lower for phrase in end_phrases)

    def _build_prompt(self, avatar_name: str, language: str, runtime_directive: str) -> str:
        prompt = self.system_prompt.replace('{avatar_name}', avatar_name)
        return f"{prompt}\n\n{runtime_directive}"

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
        """Return a deterministic opening greeting."""
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

        # Store in conversation history
        history = [{"role": "assistant", "content": opening}]
        info_state.user.update('conversation_history', history)

        return opening
