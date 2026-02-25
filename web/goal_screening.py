"""Screening goal - LLM-driven health screening using system prompt."""
import os
from datetime import datetime
from goal import Goal
from strings import MSG, BELSTR
from .config import LANGUAGE_NAMES

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
        prompt = self.system_prompt.replace('{avatar_name}', avatar_name)
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

        history.append({"role": "assistant", "content": response})
        info_state.user.update('conversation_history', history)
        msg[MSG.RESPONSE] = response

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

    def get_opening(self, info_state, lang: str = 'en', avatar_name: str = 'Assistant') -> str:
        """Generate opening greeting using LLM."""
        prompt = self.system_prompt.replace('{avatar_name}', avatar_name)
        if lang != 'en':
            lang_name = LANGUAGE_NAMES.get(lang, 'English')
            prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."

        opening = self.goal.llm.generate([], prompt)

        history = [{"role": "assistant", "content": opening}]
        info_state.user.update('conversation_history', history)

        return opening
