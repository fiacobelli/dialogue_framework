"""Session creation and management."""
import os
from decouple import config

from information_state import InformationState
from dialogue_manager_passive import DialogueManagerPassive
from .nlu_web import NLUWeb
from nlg import NLG
from rules import RuleManager
from .goal_interview import InterviewGoalManager
from .llm_provider import get_provider
from strings import BELSTR
from .config import KB_FILE, USER_MODELS_DIR, SYSTEM_PROMPT_FILE, load_prompt


def create_session(session_id: str) -> dict:
    """Initialize a new dialogue session with all required components."""
    os.makedirs(USER_MODELS_DIR, exist_ok=True)
    user_file = os.path.join(USER_MODELS_DIR, f'{session_id}.pkl')
    info_state = InformationState(user_file, KB_FILE)
    info_state.bel.add(BELSTR.DONE, False)
    info_state.user.update('session_id', session_id)

    provider_name = config('LLM_PROVIDER', default='ollama')
    provider_kwargs = {'model': config('LLM_MODEL', default='mistral:7b-instruct')}
    if provider_name == 'groq':
        provider_kwargs['api_key'] = config('GROQ_API_KEY')
    provider = get_provider(provider_name, **provider_kwargs)

    nlu = NLUWeb(info_state, provider)
    nlg = NLG()
    nlg.setup(info_state.special_texts)

    rule_mgr = RuleManager()
    rule_mgr.setup()

    goal_mgr = InterviewGoalManager(provider, load_prompt(SYSTEM_PROMPT_FILE))

    dialogue_mgr = DialogueManagerPassive()
    dialogue_mgr.setup(info_state, rule_mgr, goal_mgr)

    return {
        'info_state': info_state,
        'dialogue_mgr': dialogue_mgr,
        'goal_mgr': goal_mgr,
        'nlu': nlu,
        'nlg': nlg,
        'msg': {}
    }
