"""Configuration constants and avatar profiles."""
from decouple import config

# File paths
USER_MODELS_DIR = config('USER_MODELS_DIR', default='user_models')
PHOTOS_DIR = config('PHOTOS_DIR', default='photos')
MICROSITES_DIR = config('MICROSITES_DIR', default='static/microsites')
SYSTEM_PROMPT_FILE = config('SYSTEM_PROMPT_FILE', default='prompts/interviewer.txt')
MICROSITE_PROMPT_FILE = config('MICROSITE_PROMPT_FILE', default='prompts/microsite.txt')
KB_FILE = config('KB_FILE', default='domains/interview.json')

# Language names for LLM instruction
LANGUAGE_NAMES = {'en': 'English'} #, 'es': 'Spanish', 'ar': 'Arabic'}

# Avatar profiles for SitePal assistant
DEFAULT_AVATAR_ID = 'black_female'

AVATAR_PROFILES = {
    # Race mapping provided by Prof (W=White, L=Latino, B=Black)
    'black_female': {
        'name': 'Ludi', 'scene_id': 2756814, 'gender': 'female', 'lang': 'en',
        'race': 'B', 'engine': 11, 'language': 1, 'voice': 202,
    },
    'latina_female': {
        'name': 'Ludi', 'scene_id': 2756815, 'gender': 'female', 'lang': 'en',
        'race': 'L', 'engine': 11, 'language': 1, 'voice': 189,
    },
    'white_male': {
        'name': 'Ludi', 'scene_id': 2774645, 'gender': 'male', 'lang': 'en',
        'race': 'W', 'engine': 11, 'language': 1, 'voice': 192,
    },
    'black_male': {
        'name': 'Ludi', 'scene_id': 2774646, 'gender': 'male', 'lang': 'en',
        'race': 'B', 'engine': 11, 'language': 1, 'voice': 196,
    },
    'latino_male': {
        'name': 'Ludi', 'scene_id': 2774647, 'gender': 'male', 'lang': 'en',
        'race': 'L', 'engine': 11, 'language': 1, 'voice': 188,
    },
    'white_female': {
        'name': 'Ludi', 'scene_id': 2774648, 'gender': 'female', 'lang': 'en',
        'race': 'W', 'engine': 11, 'language': 1, 'voice': 187,
    },
}

# Server Configuration
FLASK_PORT = config('FLASK_PORT', default=5000, cast=int)
FLASK_DEBUG = config('FLASK_DEBUG', default=False, cast=bool)

# LLM Provider URLs
OLLAMA_BASE_URL = config('OLLAMA_BASE_URL', default='http://localhost:11434')
GROQ_API_URL = config('GROQ_API_URL', default='https://api.groq.com/openai/v1/chat/completions')
LLM_ERROR_MESSAGE = "I'm having trouble responding right now."

# Interview Settings
MAX_PHOTOS = config('MAX_PHOTOS', default=3, cast=int)

# Localized Strings
WELCOME_BACK = {
    'en': 'Welcome back!'
}

# Photo phase prompt (used when interview is done)
PHOTOS_PROMPT = "Thank you for sharing your story with me. Now let's add some photos to your page."

FALLBACK_PROMPT = 'You are a helpful assistant.'
