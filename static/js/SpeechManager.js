/**
 * SpeechManager - Handles speech recognition and synthesis.
 *
 * Primary: Silero VAD captures audio → Groq Whisper transcription.
 * Fallback: if VAD fails to init, reverts to continuous Web Speech API.
 */

function float32ToWav(samples) {
    const sampleRate = 16000, numChannels = 1, bytesPerSample = 2;
    const blockAlign = numChannels * bytesPerSample;
    const dataSize = samples.length * bytesPerSample;
    const buf = new ArrayBuffer(44 + dataSize);
    const v = new DataView(buf);
    const str = (off, s) => { for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i)); };
    str(0, 'RIFF'); v.setUint32(4, 36 + dataSize, true);
    str(8, 'WAVE'); str(12, 'fmt ');
    v.setUint32(16, 16, true); v.setUint16(20, 1, true);
    v.setUint16(22, numChannels, true); v.setUint32(24, sampleRate, true);
    v.setUint32(28, sampleRate * blockAlign, true); v.setUint16(32, blockAlign, true);
    v.setUint16(34, bytesPerSample * 8, true);
    str(36, 'data'); v.setUint32(40, dataSize, true);
    let off = 44;
    for (let i = 0; i < samples.length; i++, off += 2) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([buf], { type: 'audio/wav' });
}

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

        // VAD state
        this._vad = null;
        this._vadReady = false;
        this._recognitionActive = false; // true while recognition.start() is live
        this._finishing = false;         // re-entry guard for _finishListening()
        this._speechDetectedCount = 0;   // VAD fires this listen cycle; drives two-tier timer
        this._micStream = null;          // captured getUserMedia stream — stopped on destroy()

        // Research instrumentation
        this._turnEvents    = [];    // browser-side event timeline for current turn
        this._speakEndTime  = null;  // performance.now() at sitePalTalkEnded
        this._vadFireTime   = null;  // performance.now() at first VAD fire
        this._latencySource = null;  // vad | fallback | unknown
        this._speechConfidence = null; // running avg of final-result confidences

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
        this.recognition.interimResults = false;
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
            this.recordEvent('vad_init', { status: 'missing' });
            return;
        }
        let origGUM = null;
        try {
            // Temporarily wrap getUserMedia to capture the stream reference.
            // We need it to explicitly stop tracks in destroy() — VAD.destroy()
            // alone does not reliably clear the browser's mic indicator in Chrome.
            const self = this;
            origGUM = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
            navigator.mediaDevices.getUserMedia = async (constraints) => {
                const stream = await origGUM(constraints);
                self._micStream = stream;
                navigator.mediaDevices.getUserMedia = origGUM; // restore immediately
                return stream;
            };

            this._vad = await window.vad.MicVAD.new({
                baseAssetPath: '/static/js/vad/',
                onnxWASMBasePath: '/static/js/vad/',
                model: 'legacy',
                redemptionFrames: 16,
                onSpeechStart: () => this._onVADSpeechStart(),
                onSpeechEnd:   (audio) => this._onVADSpeechEnd(audio),
                onVADMisfire:  () => this._onVADMisfire(),
            });
            this._vadReady = true;
            this.recordEvent('vad_init', { status: 'ready' });
            console.log('[SpeechManager] VAD ready');
        } catch (err) {
            console.warn('[SpeechManager] VAD init failed — using continuous recognition fallback:', err);
            this.recordEvent('vad_init', { status: 'failed', message: String(err && err.message ? err.message : err) });
            this._vad = null;
            this._vadReady = false;
            if (origGUM) navigator.mediaDevices.getUserMedia = origGUM;
        }
    }

    // ── VAD callbacks ─────────────────────────────────────────────────────────

    _onVADSpeechStart() {
        this._speechDetectedCount++;
        if (this._vadFireTime === null) {
            this._vadFireTime = performance.now();
            this._latencySource = 'vad';
        }
        this.recordEvent('vad_fired', { count: this._speechDetectedCount });
        if (this.turnManager.getState() === TurnState.IDLE) {
            if (!this.turnManager.startUserTurn()) return;
            this.transcript = '';
            this.recordEvent('recognition_started');
        }
    }

    async _onVADSpeechEnd(audio) {
        this.recordEvent('vad_speech_end');
        if (this.turnManager.getState() !== TurnState.USER_SPEAKING) return;
        this._emit('silence', {});
        const wavBlob = float32ToWav(audio);
        this.recordEvent('transcribe_start');
        try {
            const sessionId = conversationAPI.getSessionId();
            const transcript = await this._transcribeWithGroq(wavBlob, sessionId);
            this.recordEvent('transcribe_done');
            this._speechDetectedCount = 0;
            if (transcript && transcript.trim()) {
                this.turnManager.endUserTurn();
                this._emit('complete', { transcript: transcript.trim() });
            } else {
                this.turnManager.reset();
                this._emit('empty', {});
            }
        } catch (err) {
            this.recordEvent('transcribe_error', { message: String(err.message || err) });
            this.turnManager.reset();
            this._emit('error', { type: 'transcribe_failed', message: String(err.message || err) });
        }
    }

    async _transcribeWithGroq(wavBlob, sessionId) {
        const form = new FormData();
        form.append('audio', wavBlob, 'audio.wav');
        if (sessionId) form.append('session_id', sessionId);
        form.append('language', this.lang.split('-')[0]);
        const resp = await fetch('/api/transcribe', { method: 'POST', body: form });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        return data.transcript || '';
    }

    _onVADMisfire() {
        this.recordEvent('vad_misfire');
        this.transcript = '';
        this._speechDetectedCount = 0;
        if (this.turnManager.getState() === TurnState.USER_SPEAKING) {
            this.turnManager.reset();
        }
    }

    // ── Recognition event handlers ────────────────────────────────────────────

    _handleResult(e) {
        this._resetSilenceTimer();
        let interim = '', final = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
            const text = e.results[i][0].transcript;
            if (e.results[i].isFinal) {
                final += text + ' ';
                // Confidence: final results only (interim values are noisy)
                const conf = e.results[i][0].confidence;
                if (conf > 0) {
                    this._speechConfidence = this._speechConfidence === null
                        ? conf : (this._speechConfidence + conf) / 2;
                }
            } else {
                interim += text;
            }
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

    /**
     * Reset the silence timer. Uses two-tier delay: SILENCE_DELAY_MS until a
     * mid-sentence VAD re-fire, then EXTENDED_SILENCE_DELAY_MS thereafter.
     * Pass an explicit delay to override (e.g. from _onVADSpeechStart).
     */
    _resetSilenceTimer(delay) {
        this._clearSilenceTimer();
        const d = delay !== undefined ? delay
            : (this._speechDetectedCount > 1 ? EXTENDED_SILENCE_DELAY_MS : SILENCE_DELAY_MS);
        this.silenceTimeout = setTimeout(() => {
            this._emit('silence', { duration: d });
            this._finishListening();
        }, d);
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
            if (this._vadReady && this._vad) this._vad.pause();
            this._recognitionActive = false;
            if (this.recognition) { try { this.recognition.stop(); } catch (_) {} }
            this.recordEvent('recognition_ended');

            const text = this.transcript.trim();
            this.transcript = '';
            this._speechDetectedCount = 0; // reset for next listen cycle

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
        this._speechDetectedCount = 0;
        this._speechConfidence = null;
        this._vadFireTime = null;
        this._latencySource = null;

        if (this._vadReady) {
            if (!this.turnManager.startUserTurn()) return false;
            this.recordEvent('recognition_started', { mode: 'vad' });
            this._vad.start();
            this._emit('listening', {});
            return true;
        }

        // Fallback: continuous recognition (original behaviour)
        if (!this.turnManager.startUserTurn()) return false;
        this.recognition.lang = this.lang;
        this._recognitionActive = true;
        this._vadFireTime = performance.now();
        this._latencySource = 'fallback';
        this.recognition.start();
        this.recordEvent('recognition_started', { mode: 'fallback' });
        this._emit('listening', {});
        return true;
    }

    /** Stop listening immediately and submit whatever was captured. */
    stopListening() {
        if (this._vadReady && this._vad) {
            this._vad.pause(); // triggers onSpeechEnd with captured audio
        } else {
            this._finishListening(); // fallback Web Speech API mode
        }
    }

    /** Speak text via SitePal / Web Speech fallback. Pauses VAD during TTS. */
    speak(text) {
        if (!text) return Promise.resolve();
        if (!this.turnManager.startSystemTurn()) {
            return Promise.reject(new Error('Cannot speak now'));
        }

        // Pause VAD so TTS audio doesn't trigger a false onSpeechStart.
        if (this._vadReady && this._vad) this._vad.pause();
        if (this.recognition) { try { this.recognition.stop(); } catch (_) {} }

        this.recordEvent('tts_started');
        this._emit('speakStart', { text });

        return new Promise((resolve) => {
            const onEnd = () => {
                document.removeEventListener('sitePalTalkEnded', onEnd);
                this._speakEndTime = performance.now(); // record before the 400 ms delay
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

    // ── Public API ────────────────────────────────────────────────────────────

    setLanguage(langCode) {
        this.lang = langCode;
        if (this.recognition) this.recognition.lang = langCode;
    }

    setVoiceConfig(config) {
        this.voiceConfig = { ...this.voiceConfig, ...config };
    }

    /** Record a browser-side event in the current turn's timeline. */
    recordEvent(eventType, metadata = {}) {
        this._turnEvents.push({
            event_type: eventType,
            client_ts_ms: Math.round(performance.now()),
            metadata
        });
    }

    /** Return and clear the current turn's event list. Call before sendMessage(). */
    consumeTurnEvents() {
        const events = this._turnEvents.slice();
        this._turnEvents = [];
        return events;
    }

    /**
     * Response latency: ms between TTS end and first VAD speech detection.
     * Returns null if either timestamp is missing (e.g. first turn of session).
     */
    getResponseLatency() {
        if (this._speakEndTime === null || this._vadFireTime === null) return null;
        return Math.round(this._vadFireTime - this._speakEndTime);
    }

    getResponseLatencySource() {
        if (this._speakEndTime === null || this._vadFireTime === null) return null;
        return this._latencySource || 'unknown';
    }

    /** Speech confidence averaged over final recognition results (0–1), or null. */
    getSpeechConfidence() {
        return this._speechConfidence;
    }

    /**
     * Pause listening — works in both VAD mode and continuous recognition fallback.
     * Stops the active listener without emitting complete/empty events.
     */
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

    /**
     * Interrupt TTS immediately. Dispatches sitePalTalkEnded so any pending
     * speak() Promise resolves cleanly and the turn state returns to IDLE.
     */
    stopSpeaking() {
        if (typeof stopSpeakText === 'function') {
            try { stopSpeakText(); } catch (_) {}
        }
        document.dispatchEvent(new Event('sitePalTalkEnded'));
    }

    /** Clean up VAD, recognition, and microphone stream at end of conversation. */
    destroy() {
        this._clearSilenceTimer();
        if (this._vad) {
            try { this._vad.pause(); }   catch (_) {}
            try { this._vad.destroy(); } catch (_) {}
            this._vad = null;
            this._vadReady = false;
        }
        if (this.recognition) { try { this.recognition.stop(); } catch (_) {} }
        // Explicitly stop all mic tracks — this is the only reliable way to clear
        // the browser's recording indicator. VAD.destroy() alone is not enough.
        if (this._micStream) {
            this._micStream.getTracks().forEach(t => { try { t.stop(); } catch (_) {} });
            this._micStream = null;
        }
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
