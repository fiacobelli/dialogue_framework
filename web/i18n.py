"""Translate patient-facing text. English is the source text and the lookup key."""
import json
import unicodedata

from .config import LANGUAGE_NAMES, STRINGS_FILE

with open(STRINGS_FILE, encoding='utf-8') as f:
    CATALOG: dict[str, dict[str, str]] = json.load(f)


def fold_accents(text: str) -> str:
    """Drop accents so 'sí' matches 'si' (ASCII text is unchanged)."""
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))


def supported_lang(lang: str | None) -> str:
    """Return lang if supported, else English."""
    return lang if lang in LANGUAGE_NAMES else 'en'


def tr(text: str, lang: str | None = 'en', **values) -> str:
    """Return text in lang (unchanged when no translation exists), with {placeholders} filled."""
    out = CATALOG.get(lang or 'en', {}).get(text, text)
    return out.format(**values) if values else out


def translator(lang: str | None):
    """Bind tr to one language, for templates: {{ t('Add Photos') }}."""
    return lambda text, **values: tr(text, lang, **values)


def language_rule(lang: str | None) -> str:
    """Prompt line asking the model to write in lang; empty for English."""
    if supported_lang(lang) == 'en':
        return ''
    return (f"\n\nIMPORTANT: Write every text value entirely in {LANGUAGE_NAMES[lang]}. "
            "Keep the JSON keys exactly as given, in English.")


def template_context(lang: str | None) -> dict:
    """Template variables for a patient page: lang, the client catalog (i18n) and t()."""
    lang = supported_lang(lang)
    return {'lang': lang, 'i18n': CATALOG.get(lang, {}), 't': translator(lang)}
