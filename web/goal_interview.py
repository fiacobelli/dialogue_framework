"""Interview goal - LLM-driven interview using system prompt."""
import os
from datetime import datetime
from goal import Goal
from strings import MSG, BELSTR
from .config import PHOTOS_PROMPT, LANGUAGE_NAMES

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

        # Add user message to history
        if user_input:
            history.append({"role": "user", "content": user_input})
            info_state.user.update('conversation_history', history)
            log_interview(session_id, f"USER: {user_input}")

        # Generate response using LLM with system prompt
        avatar_profile = info_state.user.query('avatar_profile') or {}
        avatar_name = avatar_profile.get('name', 'Assistant')
        prompt = self.system_prompt.replace('{avatar_name}', avatar_name)
        if language != 'en':
            lang_name = LANGUAGE_NAMES.get(language, 'English')
            prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."

        response = self.llm.generate(history, prompt)
        log_interview(session_id, f"LLM: {response}")

        # Check if LLM said goodbye (interview complete) - check AFTER generating
        is_ending = self._is_goodbye(response)
        log_interview(session_id, f"_is_goodbye check: {is_ending}")

        if is_ending:
            info_state.user.update('interview_phase', 'PHOTOS')
            log_interview(session_id, "PHASE CHANGED TO: PHOTOS")

        history.append({"role": "assistant", "content": response})
        info_state.user.update('conversation_history', history)
        msg[MSG.RESPONSE] = response

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

    def get_opening(self, info_state, lang: str = 'en', avatar_name: str = 'Assistant') -> str:
        """Generate opening greeting using LLM."""
        prompt = self.system_prompt.replace('{avatar_name}', avatar_name)
        if lang != 'en':
            lang_name = LANGUAGE_NAMES.get(lang, 'English')
            prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."

        # Generate opening with empty history
        opening = self.goal.llm.generate([], prompt)

        # Store in conversation history
        history = [{"role": "assistant", "content": opening}]
        info_state.user.update('conversation_history', history)

        return opening
