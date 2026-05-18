/**
 * SpeechManager - Handles speech recognition and synthesis.
 *
 * Uses Silero VAD when available to start browser speech recognition only when
 * the patient is actually speaking. Falls back to continuous recognition.
 */

class SpeechManager {
    constructor(turnManager) {
        this.turnManager = turnManager;
        this.recognition = null;
        this.synthesis = window.speechSynthesis;
        this.voices = [];
        this.transcript = '';
        this.silenceTimeout = null;
        this.listeners = {};
        this.lang = 'en-US';
        this.voiceConfig = { lang: 'en', gender: 'female' };

        this._vad = null;
        this._vadReady = false;
        this._recognitionActive = false;
        this._finishing = false;
        this._speechDetectedCount = 0;
        this._micStream = null;

        this._turnEvents = [];
        this._speakStartTime = null;
        this._speakEndTime = null;
        this._vadFireTime = null;
        this._speechConfidence = null;

        this._initRecognition();
        this._loadVoices();
    }

    _initRecognition() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            this._emit('error', { type: 'unsupported', message: 'Speech recognition not supported' });
            return;
        }
        this.recognition = new SR();
        this.recognition.continuous = true;
        this.recognition.interimResults = false;
        this.recognition.onresult = (e) => this._handleResult(e);
        this.recognition.onerror = (e) => this._handleError(e);
        this.recognition.onend = () => this._handleEnd();
    }

    _loadVoices() {
        this.voices = this.synthesis.getVoices();
        this.synthesis.onvoiceschanged = () => { this.voices = this.synthesis.getVoices(); };
    }

    async initVAD() {
        if (!window.vad || !window.vad.MicVAD) {
            console.warn('[SpeechManager] VAD library not loaded - using continuous recognition fallback');
            return;
        }

        const isSecure = window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname);
        if (!isSecure) {
            console.warn('[SpeechManager] VAD requires HTTPS - using continuous recognition fallback');
            return;
        }
        if (!navigator.mediaDevices?.getUserMedia) {
            console.warn('[SpeechManager] getUserMedia unavailable - using continuous recognition fallback');
            return;
        }

        try {
            const self = this;
            const origGUM = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
            navigator.mediaDevices.getUserMedia = async (constraints) => {
                try {
                    const stream = await origGUM(constraints);
                    self._micStream = stream;
                    return stream;
                } finally {
                    navigator.mediaDevices.getUserMedia = origGUM;
                }
            };

            const vadAssetPath = typeof appUrl === 'function' ? appUrl('/static/js/vad/') : '/static/js/vad/';
            this._vad = await window.vad.MicVAD.new({
                baseAssetPath: vadAssetPath,
                onnxWASMBasePath: vadAssetPath,
                model: 'legacy',
                onSpeechStart: () => this._onVADSpeechStart(),
                onSpeechEnd: () => {},
                onVADMisfire: () => this._onVADMisfire(),
            });
            this._vadReady = true;
            console.log('[SpeechManager] VAD ready');
        } catch (err) {
            console.warn('[SpeechManager] VAD init failed - using continuous recognition fallback:', err);
            this._vad = null;
            this._vadReady = false;
        }
    }

    _onVADSpeechStart() {
        this._speechDetectedCount++;
        this._vadFireTime = performance.now();
        this.recordEvent('vad_fired');

        if (this._recognitionActive) {
            this._resetSilenceTimer(EXTENDED_SILENCE_DELAY_MS);
            return;
        }
        if (this.turnManager.getState() !== TurnState.IDLE) return;
        if (!this.turnManager.startUserTurn()) return;

        this.transcript = '';
        this._recognitionActive = true;
        this.recognition.lang = this.lang;
        try {
            this.recognition.start();
            this.recordEvent('recognition_started');
            this._resetSilenceTimer(SILENCE_DELAY_MS);
        } catch (e) {
            console.warn('[SpeechManager] recognition.start() failed in VAD callback:', e);
            this._recognitionActive = false;
            this.turnManager.reset();
        }
    }

    _onVADMisfire() {
        if (!this._recognitionActive) return;
        this._clearSilenceTimer();
        this._recognitionActive = false;
        if (this.recognition) {
            try { this.recognition.stop(); } catch (_) {}
        }
        this.transcript = '';
        this._speechDetectedCount = 0;
        this.turnManager.reset();
    }

    _handleResult(e) {
        this._resetSilenceTimer();
        let interim = '';
        let final = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
            const text = e.results[i][0].transcript;
            if (e.results[i].isFinal) {
                final += `${text} `;
                const conf = e.results[i][0].confidence;
                if (conf > 0) {
                    this._speechConfidence = this._speechConfidence === null
                        ? conf
                        : (this._speechConfidence + conf) / 2;
                }
            } else {
                interim += text;
            }
        }
        if (final) this.transcript += final;
        this._emit('transcript', {
            final: this.transcript.trim(),
            interim,
            full: (this.transcript + interim).trim()
        });
    }

    _handleError(e) {
        this._clearSilenceTimer();
        this._emit('error', { type: e.error, message: e.message });
        this.turnManager.reset();
    }

    _handleEnd() {
        this._clearSilenceTimer();
        if (this.turnManager.getState() === TurnState.USER_SPEAKING) {
            this._finishListening();
        } else {
            this._emit('recognitionEnded', {});
        }
    }

    _resetSilenceTimer(delay) {
        this._clearSilenceTimer();
        const d = delay !== undefined
            ? delay
            : (this._speechDetectedCount > 1 ? EXTENDED_SILENCE_DELAY_MS : SILENCE_DELAY_MS);
        this.silenceTimeout = setTimeout(() => {
            this._emit('silence', { duration: d });
            this._finishListening();
        }, d);
    }

    _clearSilenceTimer() {
        if (this.silenceTimeout) {
            clearTimeout(this.silenceTimeout);
            this.silenceTimeout = null;
        }
    }

    _finishListening() {
        if (this._finishing) return;
        this._finishing = true;
        try {
            this._clearSilenceTimer();
            if (this._vadReady && this._vad) this._vad.pause();
            this._recognitionActive = false;
            if (this.recognition) {
                try { this.recognition.stop(); } catch (_) {}
            }
            this.recordEvent('recognition_ended');

            const text = this.transcript.trim();
            this.transcript = '';
            this._speechDetectedCount = 0;

            if (text) {
                this.turnManager.endUserTurn();
                this._emit('complete', { transcript: text });
            } else {
                this.recordEvent('empty_input');
                this.turnManager.reset();
                this._emit('empty', {});
            }
        } finally {
            this._finishing = false;
        }
    }

    setLanguage(langCode) {
        this.lang = langCode;
        if (this.recognition) this.recognition.lang = langCode;
    }

    setVoiceConfig(config) {
        this.voiceConfig = { ...this.voiceConfig, ...config };
    }

    startListening() {
        if (!this.recognition) {
            this._emit('error', { type: 'unsupported' });
            return false;
        }
        if (!this.turnManager.canUserSpeak()) return false;

        const isSecure = window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname);
        if (!isSecure) {
            this.turnManager.reset();
            this._emit('error', {
                type: 'insecure_context',
                message: 'Microphone access requires HTTPS. Please use the secure site.'
            });
            return false;
        }

        this.transcript = '';
        this._speechDetectedCount = 0;
        this._speechConfidence = null;

        if (this._vadReady) {
            this._vad.start();
            this._emit('listening', {});
            return true;
        }

        if (!this.turnManager.startUserTurn()) return false;
        this.recognition.lang = this.lang;
        try {
            this.recognition.start();
        } catch (err) {
            console.error('Speech recognition failed to start', err);
            this.turnManager.reset();
            this._emit('error', {
                type: err?.name || 'start_failed',
                message: 'Microphone could not start. Please ensure speech recognition is allowed for this site.'
            });
            return false;
        }
        this._emit('listening', {});
        return true;
    }

    stopListening() {
        if (this._vadReady && this._vad) this._vad.pause();
        this._finishListening();
    }

    speak(text) {
        if (!text) return Promise.resolve();
        if (!this.turnManager.startSystemTurn()) {
            return Promise.reject(new Error('Cannot speak now'));
        }

        if (this._vadReady && this._vad) this._vad.pause();
        if (this.recognition) {
            try { this.recognition.stop(); } catch (_) {}
        }

        this.recordEvent('tts_started');
        this._speakStartTime = performance.now();
        this._emit('speakStart', { text });

        return new Promise((resolve) => {
            const onEnd = () => {
                document.removeEventListener('sitePalTalkEnded', onEnd);
                this._speakEndTime = performance.now();
                this.recordEvent('tts_ended');
                this.turnManager.endSystemTurn();
                setTimeout(() => {
                    this._emit('speakEnd', { text });
                    resolve();
                }, 400);
            };
            document.addEventListener('sitePalTalkEnded', onEnd);
            speakText(text);
        });
    }

    recordEvent(type, metadata = {}) {
        this._turnEvents.push({ type, ts: Math.round(performance.now()), metadata });
    }

    consumeTurnEvents() {
        const events = this._turnEvents.slice();
        this._turnEvents = [];
        return events;
    }

    getResponseLatency() {
        if (this._speakEndTime === null || this._vadFireTime === null) return null;
        return Math.round(this._vadFireTime - this._speakEndTime);
    }

    getLastSpeakEndTime() {
        return this._speakEndTime;
    }

    getLastTtsDuration() {
        if (this._speakStartTime === null || this._speakEndTime === null) return null;
        return Math.round(this._speakEndTime - this._speakStartTime);
    }

    getSpeechConfidence() {
        return this._speechConfidence;
    }

    pauseListening() {
        this._clearSilenceTimer();
        if (this._vadReady && this._vad) {
            this._vad.pause();
        } else if (this._recognitionActive) {
            this._recognitionActive = false;
            try { this.recognition.stop(); } catch (_) {}
        }
        if (this.turnManager.getState() === TurnState.USER_SPEAKING) {
            this.turnManager.reset();
        }
    }

    stopSpeaking() {
        if (typeof stopSpeakText === 'function') {
            try { stopSpeakText(); } catch (_) {}
        }
        document.dispatchEvent(new Event('sitePalTalkEnded'));
    }

    destroy() {
        this._clearSilenceTimer();
        if (this._vad) {
            try { this._vad.pause(); } catch (_) {}
            try { this._vad.destroy(); } catch (_) {}
            this._vad = null;
            this._vadReady = false;
        }
        if (this.recognition) {
            try { this.recognition.stop(); } catch (_) {}
        }
        if (this._micStream) {
            this._micStream.getTracks().forEach(t => {
                try { t.stop(); } catch (_) {}
            });
            this._micStream = null;
        }
    }

    on(event, callback) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(callback);
    }

    off(event, callback) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }

    once(event, callback) {
        const wrapper = (data) => {
            this.off(event, wrapper);
            callback(data);
        };
        this.on(event, wrapper);
    }

    _emit(event, data) {
        if (this.listeners[event]) this.listeners[event].forEach(cb => cb(data));
    }
}
