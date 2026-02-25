"""Configuration constants and avatar profiles."""
from decouple import config

# File paths
USER_MODELS_DIR = config('USER_MODELS_DIR', default='user_models')
SYSTEM_PROMPT_FILE = config('SYSTEM_PROMPT_FILE', default='prompts/screener.txt')
CLASSIFY_PROMPT_FILE = config('CLASSIFY_PROMPT_FILE', default='prompts/classify.txt')
KB_FILE = config('KB_FILE', default='domains/screening.json')

# Language names for LLM instruction
LANGUAGE_NAMES = {'en': 'English'}

# Avatar profiles for SitePal assistant
AVATAR_PROFILES = {
    'mary': {'name': 'Mary', 'scene_id': 2756814, 'gender': 'female', 'lang': 'en'},
    'jane': {'name': 'Jane', 'scene_id': 2756815, 'gender': 'female', 'lang': 'en'},
    'laura': {'name': 'Laura', 'scene_id': 2768650, 'gender': 'female', 'lang': 'en'},
}

# Server Configuration
FLASK_PORT = config('FLASK_PORT', default=5000, cast=int)
FLASK_DEBUG = config('FLASK_DEBUG', default=False, cast=bool)

# LLM Provider URLs
OLLAMA_BASE_URL = config('OLLAMA_BASE_URL', default='http://localhost:11434')
GROQ_API_URL = config('GROQ_API_URL', default='https://api.groq.com/openai/v1/chat/completions')
LLM_ERROR_MESSAGE = "I'm having trouble responding right now."

# Localized Strings
WELCOME_BACK = {
    'en': 'Welcome back!'
}

FALLBACK_PROMPT = 'You are a helpful assistant.'
