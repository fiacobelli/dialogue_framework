from goal import Goal
from strings import MSG, BELSTR
from .config import DEFLECTION_MESSAGE
import logging


class LLMGoal(Goal):
    def __init__(self, llm_provider, system_prompt: str = None):
        self.llm = llm_provider
        self.system_prompt = system_prompt or "You are a helpful assistant."
        self.logger = logging.getLogger(__name__)

    def is_complete(self, info_state) -> bool:
        tokens = info_state.bel.query('last_tokens') or []
        return any(word in tokens for word in ['quit', 'exit', 'bye', 'goodbye'])

    def _clean_response(self, response: str) -> str:
        """If model deflected but still answered, keep only the deflection."""
        if "dialysis-related questions only" in response.lower():
            return DEFLECTION_MESSAGE
        return response

    def execute_goal(self, msg, info_state):
        history = info_state.user.query('conversation_history') or []
        user_input = msg.get(MSG.ORIG_TEXT, '')

        if user_input:
            history.append({"role": "user", "content": user_input})
            info_state.user.update('conversation_history', history)

        response = self.llm.generate(history, self.system_prompt)
        response = self._clean_response(response)

        history.append({"role": "assistant", "content": response})
        info_state.user.update('conversation_history', history)

        msg[MSG.RESPONSE] = response

    def get_next_prompt(self, msg, info_state) -> dict:
        msg[MSG.PROMPT] = msg.get(MSG.RESPONSE, "How can I help you?")
        return msg


class LLMGoalManager:
    def __init__(self, llm_provider, system_prompt: str = None):
        self.goal = LLMGoal(llm_provider, system_prompt)
        self.logger = logging.getLogger(__name__)

    def update(self, msg, info_state):
        if self.goal.is_complete(info_state):
            info_state.bel.add(BELSTR.DONE, True)
            return

        self.goal.execute_goal(msg, info_state)
        self.goal.get_next_prompt(msg, info_state)
