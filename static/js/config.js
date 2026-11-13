// URL options: ?latency=<seconds of silence that end an answer>&text=1 (show helper hints)
const URL_OPTIONS = new URLSearchParams(window.location.search);
const LATENCY_SECONDS = Math.min(10, Math.max(1, parseFloat(URL_OPTIONS.get('latency')) || 3));
const SHOW_HELPER_TEXT = URL_OPTIONS.get('text') === '1';

// Turn-finalization thresholds for automatic, low-burden patient speech input.
// These waits only start after the patient has spoken; before that, LUDI keeps listening.
const VAD_REDEMPTION_FRAMES = 10;   // ~96 ms per frame: about 1 second of silence ends a speech segment
const VAD_TAIL_MS = 960;
const TURN_IDLE_PROMPT_MS = 8000;
const TURN_POST_SPEECH_PROMPT_MS = 2500;
// Total silence before an open answer is sent = LATENCY_SECONDS (VAD tail + this grace).
const TURN_POST_SPEECH_GRACE_MS = Math.max(0, LATENCY_SECONDS * 1000 - VAD_TAIL_MS);
// Short answers (name, yes/no) are sent as soon as the VAD hears the patient stop (about 1 second).
const SHORT_ANSWER_KINDS = ['name', 'readiness'];
const SHORT_ANSWER_GRACE_MS = 0;
const TURN_MAX_WAIT_FOR_SPEECH_MS = 65000;

// Language config for speech recognition
const LANG_CONFIG = {
    'en': { recognition: 'en-US', voicePrefix: 'en' },
    'es': { recognition: 'es-US', voicePrefix: 'es' },
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
