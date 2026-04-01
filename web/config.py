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
    'mary':    {'name': 'Ludi', 'scene_id': 2756814, 'gender': 'female', 'lang': 'en'},
    'jane':    {'name': 'Ludi', 'scene_id': 2756815, 'gender': 'female', 'lang': 'en'},
    'daniel':  {'name': 'Ludi', 'scene_id': 2774645, 'gender': 'male',   'lang': 'en'},
    'robert':  {'name': 'Ludi', 'scene_id': 2774646, 'gender': 'male',   'lang': 'en'},
    'james':   {'name': 'Ludi', 'scene_id': 2774647, 'gender': 'male',   'lang': 'en'},
    'natasha': {'name': 'Ludi', 'scene_id': 2774648, 'gender': 'female', 'lang': 'en'},
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

# Database
DB_PATH = config('DB_PATH', default='db/sdoh.db')
