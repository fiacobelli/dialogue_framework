/**
 * SpeechManager - Handles speech recognition and synthesis.
 *
 * VAD (Silero) owns the mic exclusively. On speech end, audio is encoded as
 * WAV and sent to Flask /api/transcribe (Groq Whisper) for transcription.
 * This avoids the Android Chrome mic conflict that broke Web Speech API.
 */

function float32ToWav(samples) {
    const sampleRate = 16000; // VAD always resamples to 16kHz internally
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeStr = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
    writeStr(0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    writeStr(8, 'WAVE');
    writeStr(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);  // PCM
    view.setUint16(22, 1, true);  // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        offset += 2;
    }
    return new Blob([buffer], { type: 'audio/wav' });
}

class SpeechManager {
    constructor(turnManager) {
        this.turnManager = turnManager;
        this.synthesis = window.speechSynthesis;
        this.voices = [];
        this.listeners = {};
        this.lang = 'en-US';
        this.voiceConfig = { lang: 'en', gender: 'female' };

        this._vad = null;
        this._vadReady = false;
        this._micStream = null;
        this.silenceTimeout = null;

        this._audioChunks = [];
        this._commitTimer = null;
        this._transcribing = false;
        this._speechDetectedCount = 0;

        this._turnEvents = [];
        this._speakStartTime = null;
        this._speakEndTime = null;
        this._vadFireTime = null;

        this._loadVoices();
    }

    _loadVoices() {
        this.voices = this.synthesis.getVoices();
        this.synthesis.onvoiceschanged = () => { this.voices = this.synthesis.getVoices(); };
    }

    _stopMicStream() {
        if (this._micStream) {
            this._micStream.getTracks().forEach(t => {
                try { t.stop(); } catch (_) {}
            });
            this._micStream = null;
        }
    }

    async preflightMicrophone() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        const isSecure = window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname);
        const metadata = {
            status: 'checking',
            secure_context: Boolean(isSecure),
            speech_recognition_supported: Boolean(SR),
            media_devices_supported: Boolean(navigator.mediaDevices?.getUserMedia),
            vad_available: Boolean(window.vad?.MicVAD),
            permission_state: 'unsupported',
            audioinput_count: 0,
            device_labels_available: false,
            active_track_label: '',
            active_track_state: '',
            device_labels: '',
            bluetooth_input_detected: false,
        };

        if (!isSecure) {
            return { ok: false, metadata: { ...metadata, status: 'insecure_context' } };
        }
        if (!navigator.mediaDevices?.getUserMedia) {
            return { ok: false, metadata: { ...metadata, status: 'get_user_media_unsupported' } };
        }

        try {
            if (navigator.permissions?.query) {
                try {
                    const permission = await navigator.permissions.query({ name: 'microphone' });
                    metadata.permission_state = permission.state || 'unknown';
                } catch (_) {
                    metadata.permission_state = 'unsupported';
                }
            }

            this._stopMicStream();
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    echoCancellation: true,
                    autoGainControl: true,
                    noiseSuppression: true,
                }
            });
            this._micStream = stream;

            const tracks = stream.getAudioTracks();
            const activeTrack = tracks[0];
            metadata.active_track_label = activeTrack?.label || '';
            metadata.active_track_state = activeTrack?.readyState || '';

            let audioInputs = [];
            if (navigator.mediaDevices?.enumerateDevices) {
                const devices = await navigator.mediaDevices.enumerateDevices();
                audioInputs = devices.filter(device => device.kind === 'audioinput');
            }
            const labels = audioInputs.map(device => device.label).filter(Boolean);
            const labelText = labels.join(' | ');
            metadata.audioinput_count = audioInputs.length;
            metadata.device_labels_available = labels.length > 0;
            metadata.device_labels = labelText.slice(0, 500);
            metadata.bluetooth_input_detected = /bluetooth|headset|hands-free|handsfree|airpods|galaxy buds|jabra|poly|plantronics|sony|bose/i.test(labelText);

            const ok = tracks.some(track => track.readyState === 'live');
            return {
                ok,
                stream,
                metadata: {
                    ...metadata,
                    status: ok ? 'ready' : 'no_live_audio_track',
                    permission_state: metadata.permission_state === 'prompt' ? 'granted_after_prompt' : metadata.permission_state,
                }
            };
        } catch (err) {
            this._stopMicStream();
            return {
                ok: false,
                metadata: {
                    ...metadata,
                    status: 'failed',
                    error_name: err?.name || 'unknown',
                    error_message: err?.message || 'Microphone request failed',
                }
            };
        }
    }

    async initVAD(preflightStream = null) {
        if (this._vadReady && this._vad) return;
        if (!window.vad || !window.vad.MicVAD) {
            console.warn('[SpeechManager] VAD library not loaded');
            return;
        }

        const isSecure = window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname);
        if (!isSecure) {
            console.warn('[SpeechManager] VAD requires HTTPS');
            return;
        }
        if (!navigator.mediaDevices?.getUserMedia) {
            console.warn('[SpeechManager] getUserMedia unavailable');
            return;
        }

        try {
            const vadAssetPath = typeof appUrl === 'function' ? appUrl('/static/js/vad/') : '/static/js/vad/';
            let restoreGetUserMedia = null;
            const options = {
                baseAssetPath: vadAssetPath,
                onnxWASMBasePath: vadAssetPath,
                model: 'legacy',
                onSpeechStart: () => this._onVADSpeechStart(),
                onSpeechEnd: (audio) => this._onVADSpeechEnd(audio),
                onVADMisfire: () => this._onVADMisfire(),
            };
            if (preflightStream) {
                options.stream = preflightStream;
                this._micStream = preflightStream;
            } else {
                const self = this;
                const origGUM = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                restoreGetUserMedia = () => { navigator.mediaDevices.getUserMedia = origGUM; };
                navigator.mediaDevices.getUserMedia = async (constraints) => {
                    try {
                        const stream = await origGUM(constraints);
                        self._micStream = stream;
                        return stream;
                    } finally {
                        restoreGetUserMedia();
                    }
                };
            }

            try {
                this._vad = await window.vad.MicVAD.new(options);
            } finally {
                if (restoreGetUserMedia) restoreGetUserMedia();
            }
            this._vadReady = true;
            this.recordEvent('vad_init', { state: 'ready' });
            console.log('[SpeechManager] VAD ready');
        } catch (err) {
            console.warn('[SpeechManager] VAD init failed:', err);
            this._vad = null;
            this._vadReady = false;
            this.recordEvent('vad_init', { state: 'failed', reason: err?.message || 'unknown' });
        }
    }

    _onVADSpeechStart() {
        this._speechDetectedCount++;
        if (this._vadFireTime === null) {
            this._vadFireTime = performance.now();
        }
        this.recordEvent('vad_fired', { count: this._speechDetectedCount });
        this._clearSilenceTimer();
        if (!this._transcribing) {
            clearTimeout(this._commitTimer);
            this._commitTimer = null;
        }
    }

    _onVADSpeechEnd(audio) {
        this.recordEvent('vad_speech_end');
        if (this._transcribing) return;
        if (!audio || !audio.length) return;
        this._audioChunks.push(audio);
        clearTimeout(this._commitTimer);
        this._commitTimer = setTimeout(() => this._transcribeAndFinish(), 3000);
    }

    _onVADMisfire() {
        this.recordEvent('vad_misfire');
    }

    async _transcribeAndFinish() {
        this._commitTimer = null;
        if (this.turnManager.getState() !== TurnState.USER_SPEAKING) return;
        if (this._audioChunks.length === 0) {
            this.turnManager.reset();
            this._emit('empty', {});
            return;
        }
        this._transcribing = true;
        if (this._vadReady && this._vad) this._vad.pause();

        const totalLength = this._audioChunks.reduce((sum, a) => sum + a.length, 0);
        const merged = new Float32Array(totalLength);
        let off = 0;
        for (const chunk of this._audioChunks) { merged.set(chunk, off); off += chunk.length; }
        this._audioChunks = [];

        const transcribeStartedAt = performance.now();
        this.recordEvent('transcribe_started');
        try {
            const wav = float32ToWav(merged);
            const form = new FormData();
            form.append('audio', wav, 'audio.wav');
            form.append('language', this.lang.split('-')[0]);
            if (typeof conversationAPI !== 'undefined' && conversationAPI.getSessionId) {
                form.append('session_id', conversationAPI.getSessionId() || '');
            }
            if (typeof conversationAPI !== 'undefined' && conversationAPI.getPatientToken) {
                form.append('patient_token', conversationAPI.getPatientToken() || '');
            }

            const resp = await fetch(appUrl('/api/transcribe'), { method: 'POST', body: form });
            if (!resp.ok) throw new Error(`transcribe ${resp.status}`);
            const { transcript } = await resp.json();
            const text = (transcript || '').trim();

            this.recordEvent('transcribe_ended', {
                status: 'ok',
                duration_ms: Math.round(performance.now() - transcribeStartedAt),
                transcript_words: text ? text.split(/\s+/).length : 0
            });
            this.recordEvent('listening_ended', { transcript_words: text ? text.split(/\s+/).length : 0 });
            if (text && this.turnManager.getState() === TurnState.USER_SPEAKING) {
                this.turnManager.endUserTurn();
                this._emit('complete', { transcript: text });
            } else {
                this.turnManager.reset();
                this._emit('empty', {});
            }
        } catch (err) {
            this.recordEvent('transcribe_error', {
                status: 'failed',
                duration_ms: Math.round(performance.now() - transcribeStartedAt),
                error_message: err?.message || 'Transcription failed'
            });
            this.turnManager.reset();
            this._emit('empty', {});
        } finally {
            this._transcribing = false;
        }
    }

    _resetSilenceTimer(delay) {
        this._clearSilenceTimer();
        this.silenceTimeout = setTimeout(() => {
            this.recordEvent('silence_timeout', { duration_ms: delay });
            this._emit('silence', { duration: delay });
            clearTimeout(this._commitTimer);
            this._commitTimer = null;
            this._audioChunks = [];
            this.turnManager.reset();
            this._emit('empty', {});
        }, delay);
    }

    _clearSilenceTimer() {
        if (this.silenceTimeout) {
            clearTimeout(this.silenceTimeout);
            this.silenceTimeout = null;
        }
    }

    setLanguage(langCode) {
        this.lang = langCode;
    }

    setVoiceConfig(config) {
        this.voiceConfig = { ...this.voiceConfig, ...config };
    }

    startListening() {
        if (!this._vadReady) {
            this._emit('error', { type: 'vad_unavailable', message: 'Voice detection unavailable on this device.' });
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

        this._audioChunks = [];
        clearTimeout(this._commitTimer);
        this._commitTimer = null;
        this._transcribing = false;
        this._speechDetectedCount = 0;
        this._vadFireTime = null;

        this._vad.start();
        if (!this.turnManager.startUserTurn()) return false;

        this.recordEvent('listening_started');
        this._resetSilenceTimer(SILENCE_DELAY_MS);
        this._emit('listening', {});
        return true;
    }

    stopListening() {
        this._clearSilenceTimer();
        clearTimeout(this._commitTimer);
        this._commitTimer = null;
        if (this._vadReady && this._vad) this._vad.pause();
        if (this._audioChunks.length > 0 && !this._transcribing) {
            this._transcribeAndFinish();
        } else {
            this._audioChunks = [];
            this.turnManager.reset();
            this._emit('empty', {});
        }
    }

    speak(text) {
        if (!text) return Promise.resolve();
        if (!this.turnManager.startSystemTurn()) {
            return Promise.reject(new Error('Cannot speak now'));
        }

        if (this._vadReady && this._vad) this._vad.pause();

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
        return null; // Groq Whisper does not report per-utterance confidence
    }

    pauseListening() {
        this._clearSilenceTimer();
        clearTimeout(this._commitTimer);
        this._commitTimer = null;
        this._audioChunks = [];
        if (this._vadReady && this._vad) {
            this._vad.pause();
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
        clearTimeout(this._commitTimer);
        this._commitTimer = null;
        if (this._vad) {
            try { this._vad.pause(); } catch (_) {}
            try { this._vad.destroy(); } catch (_) {}
            this._vad = null;
            this._vadReady = false;
        }
        this._stopMicStream();
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
