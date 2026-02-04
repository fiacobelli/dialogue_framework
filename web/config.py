"""Configuration constants and avatar profiles."""
from decouple import config

# File paths
USER_MODELS_DIR = config('USER_MODELS_DIR', default='user_models')
PHOTOS_DIR = config('PHOTOS_DIR', default='photos')
MICROSITES_DIR = config('MICROSITES_DIR', default='static/microsites')
SYSTEM_PROMPT_FILE = config('SYSTEM_PROMPT_FILE', default='prompts/interviewer.txt')
MICROSITE_PROMPT_FILE = config('MICROSITE_PROMPT_FILE', default='prompts/microsite.txt')

# Language names for LLM instruction
LANGUAGE_NAMES = {'en': 'English'} #, 'es': 'Spanish', 'ar': 'Arabic'}

# Avatar profile for SitePal assistant
AVATAR_PROFILES = {
    'sitepal': {'name': 'Assistant', 'gender': 'female', 'lang': 'en'},
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
