/**
 * SpeechManager - Handles speech recognition and synthesis.
 *
 * Noise strategy: Silero VAD (ricky0123/vad-web) gates the Web Speech API.
 * Recognition only starts when the VAD detects the patient is actually speaking,
 * preventing ambient room chatter from being transcribed between turns.
 *
 * Fallback: if VAD fails to init, reverts to continuous recognition (original behaviour).
 */

class SpeechManager {
    constructor(turnManager) {
        this.turnManager = turnManager;
        this.recognition = null;
        this.synthesis = window.speechSynthesis;
        this.voices = [];
        this.transcript = '';
        this.silenceTimeout = null;
        this.silenceDelay = 5000; // 5 s of silence = done (elderly patients need more time)
        this.listeners = {};
        this.lang = 'en-US';
        this.voiceConfig = { lang: 'en', gender: 'female' };

        // VAD state
        this._vad = null;
        this._vadReady = false;
        this._recognitionActive = false; // true while recognition.start() is live
        this._finishing = false;         // re-entry guard for _finishListening()

        this._initRecognition();
        this._loadVoices();
        // NOTE: initVAD() is NOT called here — must be called after a user gesture.
    }

    // ── Initialisation ────────────────────────────────────────────────────────

    _initRecognition() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            this._emit('error', { type: 'unsupported', message: 'Speech recognition not supported' });
            return;
        }
        this.recognition = new SR();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.onresult = (e) => this._handleResult(e);
        this.recognition.onerror  = (e) => this._handleError(e);
        this.recognition.onend    = ()  => this._handleEnd();
    }

    _loadVoices() {
        this.voices = this.synthesis.getVoices();
        this.synthesis.onvoiceschanged = () => { this.voices = this.synthesis.getVoices(); };
    }

    /**
     * Initialise Silero VAD. Must be called after a user gesture (e.g. from
     * startConversation) so the browser permits getUserMedia.
     * Safe to call without awaiting — falls back silently on failure.
     */
    async initVAD() {
        if (!window.vad || !window.vad.MicVAD) {
            console.warn('[SpeechManager] VAD library not loaded — using continuous recognition fallback');
            return;
        }
        try {
            this._vad = await window.vad.MicVAD.new({
                baseAssetPath: '/static/js/vad/',    // worklet + model files (same-origin)
                onnxWASMBasePath: '/static/js/vad/', // ONNX Runtime WASM files
                model: 'legacy',
                // onSpeechEnd is intentionally a no-op: the 5 s silence timer submits.
                // This lets slow-speaking patients pause mid-sentence without being cut off.
                onSpeechStart: () => this._onVADSpeechStart(),
                onSpeechEnd:   () => {},
                onVADMisfire:  () => this._onVADMisfire(),
            });
            this._vadReady = true;
            console.log('[SpeechManager] VAD ready');
        } catch (err) {
            console.warn('[SpeechManager] VAD init failed — using continuous recognition fallback:', err);
            this._vad = null;
            this._vadReady = false;
        }
    }

    // ── VAD callbacks ─────────────────────────────────────────────────────────

    _onVADSpeechStart() {
        if (this._recognitionActive) return;              // already recording
        if (this.turnManager.getState() !== TurnState.IDLE) return; // not our turn
        if (!this.turnManager.startUserTurn()) return;

        this.transcript = '';
        this._recognitionActive = true;
        this.recognition.lang = this.lang;
        try {
            this.recognition.start();
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
        if (this.recognition) { try { this.recognition.stop(); } catch (_) {} }
        this.transcript = '';
        this.turnManager.reset();
    }

    // ── Recognition event handlers ────────────────────────────────────────────

    _handleResult(e) {
        this._resetSilenceTimer();
        let interim = '', final = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
            const text = e.results[i][0].transcript;
            if (e.results[i].isFinal) final += text + ' ';
            else interim += text;
        }
        if (final) this.transcript += final;
        this._emit('transcript', {
            final:   this.transcript.trim(),
            interim: interim,
            full:    (this.transcript + interim).trim()
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

    // ── Silence timer ─────────────────────────────────────────────────────────

    _resetSilenceTimer() {
        this._clearSilenceTimer();
        this.silenceTimeout = setTimeout(() => {
            this._emit('silence', { duration: this.silenceDelay });
            this._finishListening();
        }, this.silenceDelay);
    }

    _clearSilenceTimer() {
        if (this.silenceTimeout) { clearTimeout(this.silenceTimeout); this.silenceTimeout = null; }
    }

    // ── Core listen / speak ───────────────────────────────────────────────────

    _finishListening() {
        if (this._finishing) return; // prevent double-call (e.g. timer + onend race)
        this._finishing = true;
        try {
            this._clearSilenceTimer();
            if (this._vadReady && this._vad) this._vad.pause(); // stop VAD from re-triggering
            this._recognitionActive = false;
            if (this.recognition) { try { this.recognition.stop(); } catch (_) {} }

            const text = this.transcript.trim();
            this.transcript = '';

            if (text) {
                this.turnManager.endUserTurn();
                this._emit('complete', { transcript: text });
            } else {
                this.turnManager.reset();
                this._emit('empty', {});
            }
        } finally {
            this._finishing = false;
        }
    }

    /** Start listening. In VAD mode, starts the VAD monitor; recognition fires on speech. */
    startListening() {
        if (!this.recognition) {
            this._emit('error', { type: 'unsupported' });
            return false;
        }
        if (!this.turnManager.canUserSpeak()) return false;

        this.transcript = '';

        if (this._vadReady) {
            // VAD mode: TurnManager stays IDLE until VAD fires onSpeechStart.
            // UI transitions to USER_SPEAKING only when the patient actually speaks.
            this._vad.start();
            this._emit('listening', {});
            return true;
        }

        // Fallback: continuous recognition (original behaviour)
        if (!this.turnManager.startUserTurn()) return false;
        this.recognition.lang = this.lang;
        this.recognition.start();
        this._emit('listening', {});
        return true;
    }

    /** Stop listening immediately and submit whatever was captured. */
    stopListening() {
        if (this._vadReady && this._vad) this._vad.pause();
        this._finishListening();
    }

    /** Speak text via SitePal / Web Speech fallback. Pauses VAD during TTS. */
    speak(text) {
        if (!text) return Promise.resolve();
        if (!this.turnManager.startSystemTurn()) {
            return Promise.reject(new Error('Cannot speak now'));
        }

        // Pause VAD so TTS audio coming through the room speakers doesn't
        // trigger onSpeechStart and cause a false recognition session.
        if (this._vadReady && this._vad) this._vad.pause();

        if (this.recognition) { try { this.recognition.stop(); } catch (_) {} }

        this._emit('speakStart', { text });

        return new Promise((resolve) => {
            const onEnd = () => {
                document.removeEventListener('sitePalTalkEnded', onEnd);
                this.turnManager.endSystemTurn();
                // Brief delay lets residual TTS audio die before VAD/recognition restart.
                setTimeout(() => {
                    this._emit('speakEnd', { text });
                    resolve();
                }, 400);
            };
            document.addEventListener('sitePalTalkEnded', onEnd);
            speakText(text);
        });
    }

    // ── Public API ────────────────────────────────────────────────────────────

    setLanguage(langCode) {
        this.lang = langCode;
        if (this.recognition) this.recognition.lang = langCode;
    }

    setVoiceConfig(config) {
        this.voiceConfig = { ...this.voiceConfig, ...config };
    }

    /** Clean up VAD and recognition at end of conversation. */
    destroy() {
        this._clearSilenceTimer();
        if (this._vad) { this._vad.destroy(); this._vad = null; this._vadReady = false; }
        if (this.recognition) { try { this.recognition.stop(); } catch (_) {} }
    }

    // ── Event system ──────────────────────────────────────────────────────────

    on(event, callback) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(callback);
    }

    off(event, callback) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }

    once(event, callback) {
        const wrapper = (data) => { this.off(event, wrapper); callback(data); };
        this.on(event, wrapper);
    }

    _emit(event, data) {
        if (this.listeners[event]) this.listeners[event].forEach(cb => cb(data));
    }
}
