"""Screening goal - LLM-driven health screening using system prompt."""
import os
from datetime import datetime
from goal import Goal
from strings import MSG, BELSTR
from .config import LANGUAGE_NAMES, WELCOME_BACK
from . import database as db

LOGS_DIR = 'logs'


def log_screening(session_id: str, entry: str):
    """Append a log entry for debugging screenings."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    filepath = os.path.join(LOGS_DIR, f'screening_{session_id}.txt')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {entry}\n")


class ScreeningGoal(Goal):
    def __init__(self, llm_provider, system_prompt: str):
        self.llm = llm_provider
        self.system_prompt = system_prompt

    def is_complete(self, info_state) -> bool:
        return info_state.user.query('screening_phase') == 'REPORT'

    def execute_goal(self, msg, info_state):
        history = info_state.user.query('conversation_history') or []
        user_input = msg.get(MSG.ORIG_TEXT, '')
        language = info_state.user.query('language') or 'en'
        session_id = info_state.user.query('session_id') or 'unknown'

        if user_input:
            history.append({"role": "user", "content": user_input})
            info_state.user.update('conversation_history', history)
            log_screening(session_id, f"USER: {user_input}")

        avatar_profile = info_state.user.query('avatar_profile') or {}
        avatar_name = avatar_profile.get('name', 'Assistant')
        question_block = info_state.user.query('question_instructions') or DEFAULT_QUESTION_BLOCK
        prompt = self.system_prompt.replace('{avatar_name}', avatar_name)
        prompt = prompt.replace('{question_instructions}', question_block)
        last_summary = info_state.user.query('last_summary')
        if last_summary:
            prompt += f"\n\nThe patient has visited before. Summary of last session:\n{last_summary}\nAsk about any lingering issues from that session."
        if language != 'en':
            lang_name = LANGUAGE_NAMES.get(language, 'English')
            prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."

        response = self.llm.generate(history, prompt)
        log_screening(session_id, f"LLM: {response}")

        is_ending = self._is_goodbye(response)
        log_screening(session_id, f"_is_goodbye check: {is_ending}")

        if is_ending:
            info_state.user.update('screening_phase', 'REPORT')
            log_screening(session_id, "PHASE CHANGED TO: REPORT")
            summary = self.llm.generate(
                history + [{"role": "assistant", "content": response}],
                "Summarize this conversation in one paragraph, focusing on the patient's concerns and any unresolved issues.")
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
                db.save_message(visit_id, 'user', user_input, turn - 2, agent, voice)
            db.save_message(visit_id, 'assistant', response, turn - 1, agent, voice)
            db.update_visit_phase(visit_id, phase)
        if phone_pin:
            db.save_info_state(phone_pin, info_state.bel.beliefs, info_state.cg.beliefs, info_state.user.beliefs)

    def _is_goodbye(self, text: str) -> bool:
        """Check if the response signals end of screening."""
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
    def __init__(self, llm_provider, system_prompt: str):
        self.goal = ScreeningGoal(llm_provider, system_prompt)
        self.system_prompt = system_prompt

    def update(self, msg, info_state):
        if self.goal.is_complete(info_state):
            info_state.bel.add(BELSTR.DONE, True)
            return
        self.goal.execute_goal(msg, info_state)
        self.goal.get_next_prompt(msg, info_state)

    def get_opening(self, info_state, lang: str = 'en', avatar_name: str = 'Assistant', is_returning: bool = False) -> str:
        """Generate opening greeting using LLM."""
        question_block = info_state.user.query('question_instructions') or DEFAULT_QUESTION_BLOCK
        prompt = self.system_prompt.replace('{avatar_name}', avatar_name)
        prompt = prompt.replace('{question_instructions}', question_block)
        last_summary = info_state.user.query('last_summary')
        if last_summary:
            prompt += f"\n\nThe patient has visited before. Summary of last session:\n{last_summary}\nAsk about any lingering issues from that session."
        if lang != 'en':
            lang_name = LANGUAGE_NAMES.get(lang, 'English')
            prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."

        existing = info_state.user.query('conversation_history') or []
        if is_returning:
            question_text = _extract_first_question(question_block)
            greeting = WELCOME_BACK.get(lang, WELCOME_BACK['en'])
            if question_text:
                opening = f"{greeting} {question_text}"
            else:
                opening = f"{greeting} Let's continue."
        else:
            opening = self.goal.llm.generate(existing, prompt)
        existing.append({"role": "assistant", "content": opening})
        info_state.user.update('conversation_history', existing)

        phone_pin = info_state.user.query('patient_pin')
        if phone_pin:
            db.save_info_state(phone_pin, info_state.bel.beliefs, info_state.cg.beliefs, info_state.user.beliefs)

        return opening


def _extract_first_question(question_block: str) -> str | None:
    """Return the text of the first numbered question from the block."""
    if not question_block:
        return None
    for line in question_block.splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        # Expect format like: 7. "Question text"
        parts = line.split('.', 1)
        if len(parts) != 2:
            continue
        remainder = parts[1].strip()
        if remainder.startswith('"') and remainder.endswith('"') and len(remainder) > 2:
            return remainder[1:-1]
        return remainder
    return None


DEFAULT_QUESTION_BLOCK = "\n".join([
    '1. "What is your living situation today? Do you have a steady place to live?"',
    '2. "Within the past 12 months, have you worried that your food would run out before you got money to buy more?"',
    '3. "Over the past 2 weeks, how often have you felt down, depressed, or hopeless?"',
    '4. "Do you feel physically and emotionally safe where you currently live?"',
    '5. "In a typical week, how many days do you do any physical activity like walking or exercise?"',
    '6. "Do you need help with daily activities such as bathing, preparing meals, shopping, or managing medications?"',
])
