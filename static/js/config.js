// Silence thresholds for two-tier VAD timer.
const SILENCE_DELAY_MS = 2500;
const EXTENDED_SILENCE_DELAY_MS = 4000;

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
