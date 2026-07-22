"""Session creation and management."""
import os
from decouple import config

from information_state import InformationState
from dialogue_manager_passive import DialogueManagerPassive
from .nlu_web import NLUWeb
from nlg import NLG
from rules import RuleManager
from .goal_screening import ScreeningGoalManager
from .llm_provider import get_provider
from strings import BELSTR
from .config import (
    KB_FILE,
    USER_MODELS_DIR,
    SYSTEM_PROMPT_FILE,
    FIRST_TIME_PROMPT_FILE,
    SUBSEQUENT_PROMPT_FILE,
    LLM_MODEL,
    LLM_FALLBACK_MODEL,
)
from . import database as db


def load_prompt(filepath: str) -> str:
    """Load system prompt from file, with fallback."""
    try:
        with open(filepath, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return 'You are a helpful assistant.'


def create_session(session_id: str) -> dict:
    """Initialize a new dialogue session with all required components."""
    user_file = os.path.join(USER_MODELS_DIR, f'{session_id}.pkl')
    info_state = InformationState(user_file, KB_FILE)
    info_state.bel.add(BELSTR.DONE, False)
    info_state.user.update('session_id', session_id)

    saved = db.load_info_state(session_id)
    if saved:
        for k, v in saved['beliefs'].items():
            info_state.bel.beliefs[k] = v
        for k, v in saved['common_ground'].items():
            info_state.cg.beliefs[k] = v
        for k, v in saved['user_model'].items():
            info_state.user.beliefs[k] = v

    nlu = NLUWeb()
    nlg = NLG()
    nlg.setup(info_state.special_texts)

    rule_mgr = RuleManager()
    rule_mgr.setup()

    provider_name = config('LLM_PROVIDER', default='ollama')
    default_model = 'openai/gpt-oss-120b' if provider_name == 'groq' else 'mistral:7b-instruct'
    provider_kwargs = {'model': LLM_MODEL or default_model}
    if provider_name == 'groq':
        api_key = config('GROQ_API_KEY', default=None)
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY is not set. "
                "Add it to your .env file or export it before starting the server."
            )
        provider_kwargs['api_key'] = api_key
        if LLM_FALLBACK_MODEL:
            provider_kwargs['fallback_model'] = LLM_FALLBACK_MODEL
    provider = get_provider(provider_name, **provider_kwargs)
    goal_mgr = ScreeningGoalManager(
        provider,
        load_prompt(SYSTEM_PROMPT_FILE),
        load_prompt(FIRST_TIME_PROMPT_FILE),
        load_prompt(SUBSEQUENT_PROMPT_FILE),
    )

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
