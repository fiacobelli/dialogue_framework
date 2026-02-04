"""Interview goal - LLM-driven interview using system prompt."""
from goal import Goal
from strings import MSG, BELSTR
from .config import PHOTOS_PROMPT, LANGUAGE_NAMES


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

        # Add user message to history
        if user_input:
            history.append({"role": "user", "content": user_input})
            info_state.user.update('conversation_history', history)

        # Generate response using LLM with Prof's system prompt
        prompt = self.system_prompt
        if language != 'en':
            lang_name = LANGUAGE_NAMES.get(language, 'English')
            prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."

        response = self.llm.generate(history, prompt)

        # Check if LLM said goodbye (interview complete) - check AFTER generating
        if self._is_goodbye(response):
            info_state.user.update('interview_phase', 'PHOTOS')

        history.append({"role": "assistant", "content": response})
        info_state.user.update('conversation_history', history)
        msg[MSG.RESPONSE] = response

    def _is_goodbye(self, text: str) -> bool:
        """Check if the response is a goodbye."""
        text_lower = text.lower()
        goodbye_phrases = ['goodbye', 'bye', 'thank you for sharing', 'take care']
        return any(phrase in text_lower for phrase in goodbye_phrases)

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
        prompt = self.system_prompt
        if lang != 'en':
            lang_name = LANGUAGE_NAMES.get(lang, 'English')
            prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}."

        # Generate opening with empty history
        opening = self.goal.llm.generate([], prompt)

        # Store in conversation history
        history = [{"role": "assistant", "content": opening}]
        info_state.user.update('conversation_history', history)

        return opening
