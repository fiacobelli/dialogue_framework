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
AZURE_OPENAI_BASE_URL = config(
    'AZURE_OPENAI_BASE_URL',
    default='https://luc-research-ai-resource.services.ai.azure.com/openai/v1/',
)
AZURE_OPENAI_API_KEY = config('AZURE_OPENAI_API_KEY', default='')
LLM_ERROR_MESSAGE = "I'm having trouble responding right now."

# Provider + model. One model serves both the interview turns and the one-shot
# microsite generation.
LLM_PROVIDER = config('LLM_PROVIDER', default='azure_openai')
LLM_MODEL = config('LLM_MODEL', default='gpt-6-astra')
LLM_FALLBACK_MODEL = config('LLM_FALLBACK_MODEL', default='')

# Interview Settings
MAX_PHOTOS = config('MAX_PHOTOS', default=3, cast=int)
MAX_PHOTO_UPLOAD_BYTES = config('MAX_PHOTO_UPLOAD_BYTES', default=10 * 1024 * 1024, cast=int)

# Donor microsite — static campaign copy (config over hardcoding)
MICROSITE_IMPACT_ITEMS = [
    {'icon': 'shield-check', 'title': 'Guided by experts',
     'blurb': 'Living donation is led by a qualified transplant team, every step of the way.'},
    {'icon': 'info', 'title': 'Learn with no pressure',
     'blurb': 'Anyone can explore what donation involves before deciding anything.'},
    {'icon': 'heart', 'title': 'A life-changing gift',
     'blurb': 'One living donor can restore health, energy, and time with family.'},
    {'icon': 'people', 'title': 'More than one life',
     'blurb': 'Your decision can give a whole family new hope for the future.'},
    {'icon': 'shield-check', 'title': 'Medical evaluation',
     'blurb': 'Potential donors are carefully evaluated for health and safety before donation.'},
    {'icon': 'info', 'title': 'Questions are welcome',
     'blurb': 'A transplant team can explain risks, recovery, timing, and available resources.'},
    {'icon': 'people', 'title': 'Family support matters',
     'blurb': 'Sharing this page helps more people understand the need and talk it through.'},
    {'icon': 'heart', 'title': 'Every share can help',
     'blurb': 'Even people who cannot donate may know someone willing to learn more.'},
]

MICROSITE_NEXT_STEPS = [
    {'title': 'Share this page',
     'blurb': 'Send it to people who might help, or who may know someone who can.'},
    {'title': 'Learn about living donation',
     'blurb': 'Understand what donation involves, with no obligation to continue.'},
    {'title': 'Talk with a transplant team',
     'blurb': 'Qualified professionals guide anyone who wants to explore donating.'},
]

# Localized Strings
WELCOME_BACK = {
    'en': 'Welcome back!'
}

FALLBACK_PROMPT = 'You are a helpful assistant.'


def load_prompt(filepath: str, fallback: str = FALLBACK_PROMPT) -> str:
    """Read a prompt/text file, returning a fallback if it is missing."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return fallback


def clean_text(value) -> str:
    """Coerce a value to a stripped string (empty for None/falsy)."""
    return str(value or '').strip()
