"""Configuration constants and avatar profiles."""
from decouple import config

# File paths
USER_MODELS_DIR = config('USER_MODELS_DIR', default='user_models')
PHOTOS_DIR = config('PHOTOS_DIR', default='photos')
MICROSITES_DIR = config('MICROSITES_DIR', default='static/microsites')
DB_PATH = config('DB_PATH', default='db/transplant.db')
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
ADMIN_USERNAME = config('ADMIN_USERNAME', default='admin')
ADMIN_PASSWORD = config('ADMIN_PASSWORD', default='')

# LLM Provider URLs
OLLAMA_BASE_URL = config('OLLAMA_BASE_URL', default='http://localhost:11434')
GROQ_API_URL = config('GROQ_API_URL', default='https://api.groq.com/openai/v1/chat/completions')
GROQ_API_KEY = config('GROQ_API_KEY', default='')
GROQ_WHISPER_URL = config('GROQ_WHISPER_URL', default='https://api.groq.com/openai/v1/audio/transcriptions')
LLM_ERROR_MESSAGE = "I'm having trouble responding right now."

# Interview Settings
MAX_PHOTOS = config('MAX_PHOTOS', default=3, cast=int)
MAX_PHOTO_UPLOAD_BYTES = config('MAX_PHOTO_UPLOAD_BYTES', default=10 * 1024 * 1024, cast=int)
INTERVIEW_EVIDENCE_SHADOW = config('INTERVIEW_EVIDENCE_SHADOW', default=True, cast=bool)
# When True, use the single-call LLM interview turn (web/interview_turn.py) instead
# of the legacy classifier/policy/flow pipeline. Default off until cutover (Phase 2).
INTERVIEW_LLM_TURN = config('INTERVIEW_LLM_TURN', default=False, cast=bool)
INTERVIEW_SEMANTIC_RESPONSE_PLAN = config('INTERVIEW_SEMANTIC_RESPONSE_PLAN', default=False, cast=bool)
EVIDENCE_INTERPRETER_PROMPT_VERSION = 'evidence-interpreter-v1'

# Localized Strings
WELCOME_BACK = {
    'en': 'Welcome back!'
}

# Photo phase prompt (used when interview is done)
PHOTOS_PROMPT = "Thank you for sharing your story with me. Now let's add some photos to your page."

FALLBACK_PROMPT = 'You are a helpful assistant.'
