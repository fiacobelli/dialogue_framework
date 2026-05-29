"""Interview goal - LLM-driven interview using the single-call turn."""
import uuid
from goal import Goal
from strings import MSG, BELSTR
from .interview_state import build_interview_state


class InterviewGoal(Goal):
    def __init__(self, llm_provider, system_prompt: str):
        self.llm = llm_provider
        self.system_prompt = system_prompt

    def is_complete(self, info_state) -> bool:
        return info_state.user.query('interview_phase') == 'PHOTOS'

    def execute_goal(self, msg, info_state):
        # Imported lazily: interview_turn -> microsite -> session_store would cycle at load time.
        from .interview_turn import run_turn
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
