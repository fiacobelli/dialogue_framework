// Turn-finalization thresholds for automatic, low-burden patient speech input.
const TURN_IDLE_PROMPT_MS = 8000;
const TURN_POST_SPEECH_GRACE_MS = 3800;
const TURN_EXTENDED_POST_SPEECH_GRACE_MS = 6500;
const TURN_MAX_SPEECH_AUDIO_MS = 28000;
const TURN_MAX_TURN_MS = 65000;

// Language config for speech recognition
const LANG_CONFIG = {
    'en': { recognition: 'en-US', voicePrefix: 'en' },
    'es': { recognition: 'es-ES', voicePrefix: 'es' },
    'ar': { recognition: 'ar-SA', voicePrefix: 'ar' }
};

// App-relative URL helpers. APP_BASE_PATH is injected by Flask templates and
// is "/microsite" in production, or "" during root-mounted local development.
window.APP_BASE_PATH = (window.APP_BASE_PATH || '').replace(/\/$/, '');

function appUrl(path = '/') {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    if (
        window.APP_BASE_PATH
        && (normalizedPath === window.APP_BASE_PATH || normalizedPath.startsWith(`${window.APP_BASE_PATH}/`))
    ) {
        return normalizedPath;
    }
    return `${window.APP_BASE_PATH}${normalizedPath}`;
}

function absoluteAppUrl(path = '/') {
    return new URL(appUrl(path), window.location.origin).toString();
}
