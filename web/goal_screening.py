"""Screening goal - LLM-driven health screening using system prompt."""
import os
import re
import time
from datetime import datetime
from goal import Goal
from strings import MSG, BELSTR
from .config import LANGUAGE_NAMES
from . import database as db

LOGS_DIR = 'logs'
MAX_USER_TURNS = 20
MIN_TURNS_FOR_GOODBYE = 4

# Words/phrases that indicate a surface-level answer not worth acting on
_SURFACE_ANSWERS = frozenset({
    'yes', 'no', 'fine', 'okay', 'ok', 'good', 'bad', 'great', 'maybe',
    'sure', 'yeah', 'nope', 'not really', 'kind of', 'i guess', 'alright',
    "i don't know", 'i dont know', 'satisfied', 'not bad', 'nothing',
    'none', 'never', 'always', 'not much', 'a little', 'sort of',
})

_PROBE_INJECTION = (
    "\n\nCRITICAL — DO NOT SKIP: The patient's last answer was too short or "
    "vague to be clinically useful. You MUST ask exactly one specific follow-up "
    "question about what they said before moving to the next topic. "
    "Do NOT ask the next screening topic yet."
)


def _is_surface_answer(text: str) -> bool:
    """Return True if the answer is too brief or vague to be actionable."""
    t = text.strip().lower().rstrip('.,!?')
    if not t:
        return False
    if t in _SURFACE_ANSWERS:
        return True
    # Three words or fewer is always surface-level
    if len(t.split()) <= 3:
        return True
    return False


EXIT_PHRASE = "Thank you for sharing that with me. Let me review your answers."
SUMMARY_PREAMBLE_RE = re.compile(
    r"^\s*(I['\u2019]ll|I will|Here['\u2019]s|Here is|Sure|Okay|Of course|Certainly)[^.\n]*[.!?]\s*",
    re.IGNORECASE,
)


def log_screening(session_id: str, entry: str):
    """Append a log entry for debugging screenings."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    filepath = os.path.join(LOGS_DIR, f'screening_{session_id}.txt')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {entry}\n")


class ScreeningGoal(Goal):
    def __init__(self, llm_provider, system_prompt: str, first_time_prompt: str = '', subsequent_prompt: str = ''):
        self.llm = llm_provider
        self.system_prompt = system_prompt
        self.first_time_prompt = first_time_prompt
        self.subsequent_prompt = subsequent_prompt

    def is_complete(self, info_state) -> bool:
        return info_state.user.query('screening_phase') == 'REPORT'

    def _build_prompt(self, info_state, avatar_name: str, language: str) -> str:
        """Concatenate the right intro + shared screener + runtime values."""
        visit_number = info_state.user.query('visit_number') or 1
        is_returning = visit_number > 1
        intro = self.subsequent_prompt if is_returning else self.first_time_prompt
        full = f"{intro}\n\n{self.system_prompt}" if intro else self.system_prompt

        question_block = info_state.user.query('question_instructions') or DEFAULT_QUESTION_BLOCK
        prompt = full.replace('{avatar_name}', avatar_name)
        prompt = prompt.replace('{question_instructions}', question_block)
        last_summary = info_state.user.query('last_summary')
        if is_returning and last_summary:
            prompt += f"\n\nSummary of last session:\n{last_summary}"
        if language != 'en':
            lang_name = LANGUAGE_NAMES.get(language, 'English')
            prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."
        return prompt

    def execute_goal(self, msg, info_state):
        history = info_state.user.query('conversation_history') or []
        user_input = msg.get(MSG.ORIG_TEXT, '')
        language = info_state.user.query('language') or 'en'
        session_id = info_state.user.query('session_id') or 'unknown'
        turn_meta = msg.get('turn_meta') or {}
        no_response = turn_meta.get('no_response', False)

        if user_input:
            history.append({"role": "user", "content": user_input})
            info_state.user.update('conversation_history', history)
            log_screening(session_id, f"USER: {user_input}")

        user_turn_count = sum(1 for m in history if m.get('role') == 'user')
        avatar_profile = info_state.user.query('avatar_profile') or {}
        avatar_name = avatar_profile.get('name', 'Assistant')
        prompt = self._build_prompt(info_state, avatar_name, language)

        # If the patient gave a surface-level answer, inject a hard probe
        # instruction into the system prompt for this turn only.
        # Code-enforced because small LLMs reliably ignore complex prompt rules.
        effective_prompt = prompt
        if user_input and _is_surface_answer(user_input):
            effective_prompt = prompt + _PROBE_INJECTION
            log_screening(session_id, f"PROBE INJECTED for surface answer: '{user_input}'")

        t0 = time.perf_counter()
        response = self.llm.generate(history, effective_prompt)
        llm_latency_ms = int((time.perf_counter() - t0) * 1000)
        log_screening(session_id, f"LLM ({llm_latency_ms}ms): {response}")

        is_ending = self._is_goodbye(response, user_turn_count)
        if not is_ending and user_turn_count >= MAX_USER_TURNS:
            log_screening(session_id, f"FORCED ENDING at turn {user_turn_count}")
            response = EXIT_PHRASE
            is_ending = True
        log_screening(session_id, f"_is_goodbye check: {is_ending}")

        if is_ending:
            info_state.user.update('screening_phase', 'REPORT')
            log_screening(session_id, "PHASE CHANGED TO: REPORT")
            summary = self._generate_summary(history, response)
            info_state.user.update('last_summary', summary)
            log_screening(session_id, f"SUMMARY: {summary}")

        history.append({"role": "assistant", "content": response})
        info_state.user.update('conversation_history', history)
        msg[MSG.RESPONSE] = response

        visit_id = info_state.user.query('visit_id')
        phone_pin = info_state.user.query('patient_pin')
        phase = info_state.user.query('screening_phase') or 'WELCOME'
        agent = info_state.user.query('avatar') or 'unknown'
        voice = avatar_profile.get('lang', language)
        if visit_id:
            turn = len(history)
            if user_input:
                db.save_message(
                    visit_id, 'user', user_input, turn - 2, agent, voice,
                    input_modality=turn_meta.get('input_modality'),
                    response_latency_ms=turn_meta.get('response_latency_ms'),
                    speech_confidence=turn_meta.get('speech_confidence'),
                    client_sent_at=turn_meta.get('client_sent_at'),
                )
                if not no_response:
                    db.increment_visit_turns(visit_id)
                    events = turn_meta.get('events') or []
                    if events:
                        db.save_turn_events(visit_id, turn - 2, events)
            db.save_message(
                visit_id, 'assistant', response, turn - 1, agent, voice,
                llm_latency_ms=llm_latency_ms,
            )
            db.update_visit_phase(visit_id, phase)
        if phone_pin:
            db.save_info_state(phone_pin, info_state.bel.beliefs, info_state.cg.beliefs, info_state.user.beliefs)

    def _generate_summary(self, history: list, last_response: str) -> str:
        """Ask the LLM for a one-paragraph summary. Strip any preamble."""
        instruction = (
            "Write a one-paragraph summary of the conversation above. "
            "List the topics that were discussed (for example: housing, food, "
            "transportation, financial strain, kidney disease burden, family support), "
            "what the patient said about each, and any concerns or positive notes. "
            "Start directly with the content. Do NOT preface with phrases like "
            "'Here is a summary', 'I'll summarize', 'Sure', or similar."
        )
        full_history = history + [{"role": "assistant", "content": last_response}]
        raw = self.llm.generate(full_history, instruction)
        cleaned = SUMMARY_PREAMBLE_RE.sub('', raw or '', count=1)
        return cleaned.strip()

    def _is_goodbye(self, text: str, user_turn_count: int) -> bool:
        """Check if the response signals end of screening (with min-turn guard)."""
        if user_turn_count < MIN_TURNS_FOR_GOODBYE:
            return False
        text_lower = text.lower()
        end_phrases = [
            'thank you for sharing that with me',
            'let me review your answers',
            'thank you for sharing all of that',
            'the right people follow up',
            'make sure the right people',
        ]
        return any(phrase in text_lower for phrase in end_phrases)

    def get_next_prompt(self, msg, info_state) -> dict:
        msg[MSG.PROMPT] = msg.get(MSG.RESPONSE, '')
        return msg


class ScreeningGoalManager:
    def __init__(self, llm_provider, system_prompt: str, first_time_prompt: str = '', subsequent_prompt: str = ''):
        self.goal = ScreeningGoal(llm_provider, system_prompt, first_time_prompt, subsequent_prompt)
        self.system_prompt = system_prompt
        self.first_time_prompt = first_time_prompt
        self.subsequent_prompt = subsequent_prompt

    def update(self, msg, info_state):
        if self.goal.is_complete(info_state):
            info_state.bel.add(BELSTR.DONE, True)
            return
        self.goal.execute_goal(msg, info_state)
        self.goal.get_next_prompt(msg, info_state)

    def get_opening(self, info_state, lang: str = 'en', avatar_name: str = 'Assistant', is_returning: bool = False) -> str:
        """Generate opening greeting using LLM."""
        prompt = self.goal._build_prompt(info_state, avatar_name, lang)
        existing = info_state.user.query('conversation_history') or []
        opening = self.goal.llm.generate(existing, prompt)
        existing.append({"role": "assistant", "content": opening})
        info_state.user.update('conversation_history', existing)

        phone_pin = info_state.user.query('patient_pin')
        if phone_pin:
            db.save_info_state(phone_pin, info_state.bel.beliefs, info_state.cg.beliefs, info_state.user.beliefs)

        return opening


DEFAULT_QUESTION_BLOCK = "\n".join([
    'Housing: "What is your living situation today? Do you have a steady place to live?"',
    'Food: "Within the past 12 months, have you worried that your food would run out before you got money to buy more?"',
    'Safety: "Do you feel physically and emotionally safe where you currently live?"',
    'Daily Living: "Do you need help with daily activities such as bathing, preparing meals, shopping, or managing medications?"',
])
