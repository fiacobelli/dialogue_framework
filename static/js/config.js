// Silence thresholds for two-tier VAD timer (field-adjustable constants)
const SILENCE_DELAY_MS = 2500;           // ms after first VAD fire before auto-submit
const EXTENDED_SILENCE_DELAY_MS = 4000;  // ms after a mid-sentence VAD re-fire

// Language config for speech recognition
const LANG_CONFIG = {
    'en': { recognition: 'en-US', voicePrefix: 'en' },
    'es': { recognition: 'es-ES', voicePrefix: 'es' },
    'ar': { recognition: 'ar-SA', voicePrefix: 'ar' }
};
