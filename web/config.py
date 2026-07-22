"""Configuration constants and avatar profiles."""
from decouple import config

# File paths
USER_MODELS_DIR = config('USER_MODELS_DIR', default='user_models')
SYSTEM_PROMPT_FILE = config('SYSTEM_PROMPT_FILE', default='prompts/screener.txt')
FIRST_TIME_PROMPT_FILE = config('FIRST_TIME_PROMPT_FILE', default='prompts/first_time.txt')
SUBSEQUENT_PROMPT_FILE = config('SUBSEQUENT_PROMPT_FILE', default='prompts/subsequent.txt')
QUESTIONS_FILE = config('QUESTIONS_FILE', default='prompts/questions.txt')
CLASSIFY_PROMPT_FILE = config('CLASSIFY_PROMPT_FILE', default='prompts/classify.txt')
KB_FILE = config('KB_FILE', default='domains/screening.json')

# Language names for LLM instruction
LANGUAGE_NAMES = {'en': 'English'}

# Avatar profiles for SitePal assistant
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
LLM_MODEL = config('LLM_MODEL', default='')
LLM_FALLBACK_MODEL = config('LLM_FALLBACK_MODEL', default='')

# Localized Strings
WELCOME_BACK = {
    'en': 'Welcome back!'
}

FALLBACK_PROMPT = 'You are a helpful assistant.'

# Database
DB_PATH = config('DB_PATH', default='db/sdoh.db')

# Groq Whisper transcription
GROQ_API_KEY = config('GROQ_API_KEY', default='')
GROQ_WHISPER_URL = config('GROQ_WHISPER_URL', default='https://api.groq.com/openai/v1/audio/transcriptions')

# Email report (sent after each classify)
EMAIL_ENABLED    = config('EMAIL_ENABLED',    default=False, cast=bool)
SMTP_HOST        = config('SMTP_HOST',        default='smtp.office365.com')
SMTP_PORT        = config('SMTP_PORT',        default=587, cast=int)
EMAIL_SENDER     = config('EMAIL_SENDER',     default='')
EMAIL_PASSWORD   = config('EMAIL_PASSWORD',   default='')
EMAIL_RECIPIENTS = config('EMAIL_RECIPIENTS', default='fiacobelli@luc.edu')
