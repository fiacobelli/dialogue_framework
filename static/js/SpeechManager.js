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
        this.synthesis = window.speechSynthesis || null;
        this.voices = [];
        this.listeners = {};
        this.lang = 'en-US';
        this.voiceConfig = { lang: 'en', gender: 'female' };

        this._vad = null;
        this._vadReady = false;
        this._micStream = null;

        this._audioChunks = [];
        this._transcribing = false;
        this._speechDetectedCount = 0;
        this._finalizationSnapshot = {};
        this._finalizer = new TurnFinalizer({
            onIdlePrompt: (snapshot) => this._onTurnIdlePrompt(snapshot),
            onPostSpeechPrompt: (snapshot) => this._onPostSpeechPrompt(snapshot),
            onCommit: (snapshot) => this._commitFinalizedAudio(snapshot),
            onAbort: (snapshot) => this._abortListening(snapshot),
        });

        this._turnEvents = [];
        this._speakStartTime = null;
        this._speakEndTime = null;
        this._vadFireTime = null;

        this._loadVoices();
    }

    _log(step, details = {}) {
        let payload = '';
        try {
            payload = JSON.stringify(details);
        } catch (_) {
            payload = String(details || '');
        }
        console.info(`[SpeechManager] ${step} ${payload}`);
    }

    _loadVoices() {
        if (!this.synthesis || typeof this.synthesis.getVoices !== 'function') {
            this.voices = [];
            console.warn('[SpeechManager] speechSynthesis unavailable; using fallback voice handling');
            return;
        }
        this.voices = this.synthesis.getVoices();
        if ('onvoiceschanged' in this.synthesis) {
            this.synthesis.onvoiceschanged = () => {
                try {
                    this.voices = this.synthesis.getVoices();
                } catch (_) {
                    this.voices = [];
                }
            };
        }
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

        this._log('preflight:start', {
            secure_context: metadata.secure_context,
            speech_recognition_supported: metadata.speech_recognition_supported,
            media_devices_supported: metadata.media_devices_supported,
            vad_available: metadata.vad_available,
        });

        if (!isSecure) {
            this._log('preflight:blocked', { reason: 'insecure_context' });
            return { ok: false, metadata: { ...metadata, status: 'insecure_context' } };
        }
        if (!navigator.mediaDevices?.getUserMedia) {
            this._log('preflight:blocked', { reason: 'get_user_media_unsupported' });
            return { ok: false, metadata: { ...metadata, status: 'get_user_media_unsupported' } };
        }

        try {
            if (navigator.permissions?.query) {
                try {
                    const permission = await navigator.permissions.query({ name: 'microphone' });
                    metadata.permission_state = permission.state || 'unknown';
                    this._log('preflight:permission-state', { state: metadata.permission_state });
                } catch (_) {
                    metadata.permission_state = 'unsupported';
                    this._log('preflight:permission-state', { state: 'unsupported' });
                }
            }

            this._stopMicStream();
            const preferredConstraints = {
                audio: {
                    channelCount: 1,
                    echoCancellation: true,
                    autoGainControl: true,
                    noiseSuppression: true,
                }
            };
            const fallbackConstraints = { audio: true };
            let stream;
            try {
                this._log('preflight:getUserMedia:start', { mode: 'preferred', constraints: preferredConstraints });
                stream = await navigator.mediaDevices.getUserMedia(preferredConstraints);
                metadata.capture_mode = 'preferred';
            } catch (firstErr) {
                this._log('preflight:getUserMedia:error', {
                    mode: 'preferred',
                    error_name: firstErr?.name || 'unknown',
                    error_message: firstErr?.message || 'Microphone request failed',
                });
                const shouldRetry = ['NotReadableError', 'OverconstrainedError', 'AbortError'].includes(firstErr?.name);
                if (!shouldRetry) throw firstErr;
                try {
                    this._log('preflight:getUserMedia:start', { mode: 'fallback', constraints: fallbackConstraints });
                    stream = await navigator.mediaDevices.getUserMedia(fallbackConstraints);
                    metadata.capture_mode = 'fallback';
                } catch (fallbackErr) {
                    fallbackErr.first_error_name = firstErr?.name || 'unknown';
                    fallbackErr.first_error_message = firstErr?.message || 'Microphone request failed';
                    throw fallbackErr;
                }
            }
            this._micStream = stream;
            this._log('preflight:getUserMedia:success', {
                mode: metadata.capture_mode || 'unknown',
                track_count: stream.getAudioTracks().length,
            });

            const tracks = stream.getAudioTracks();
            const activeTrack = tracks[0];
            metadata.active_track_label = activeTrack?.label || '';
            metadata.active_track_state = activeTrack?.readyState || '';
            metadata.active_track_enabled = Boolean(activeTrack?.enabled);
            metadata.active_track_muted = Boolean(activeTrack?.muted);
            this._log('preflight:track', {
                label: metadata.active_track_label,
                state: metadata.active_track_state,
                enabled: metadata.active_track_enabled,
                muted: metadata.active_track_muted,
            });

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
            this._log('preflight:devices', {
                audioinput_count: metadata.audioinput_count,
                labels_available: metadata.device_labels_available,
                bluetooth_input_detected: metadata.bluetooth_input_detected,
                labels: metadata.device_labels,
            });

            const ok = tracks.some(track => track.readyState === 'live');
            this._log('preflight:result', {
                ok,
                status: ok ? 'ready' : 'no_live_audio_track',
            });
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
            this._log('preflight:error', {
                error_name: err?.name || 'unknown',
                error_message: err?.message || 'Microphone request failed',
                first_error_name: err?.first_error_name || '',
                first_error_message: err?.first_error_message || '',
            });
            this._stopMicStream();
            return {
                ok: false,
                metadata: {
                    ...metadata,
                    status: 'failed',
                    error_name: err?.name || 'unknown',
                    error_message: err?.message || 'Microphone request failed',
                    first_error_name: err?.first_error_name || '',
                    first_error_message: err?.first_error_message || '',
                }
            };
        }
    }

    async initVAD(preflightStream = null) {
        if (this._vadReady && this._vad) return;
        if (!window.vad || !window.vad.MicVAD) {
            console.warn('[SpeechManager] VAD library not loaded');
            this._log('vad:init:blocked', { reason: 'library_not_loaded' });
            return;
        }

        const isSecure = window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname);
        if (!isSecure) {
            console.warn('[SpeechManager] VAD requires HTTPS');
            this._log('vad:init:blocked', { reason: 'insecure_context' });
            return;
        }
        if (!navigator.mediaDevices?.getUserMedia) {
            console.warn('[SpeechManager] getUserMedia unavailable');
            this._log('vad:init:blocked', { reason: 'get_user_media_unavailable' });
            return;
        }

        try {
            this._log('vad:init:start', { has_preflight_stream: Boolean(preflightStream) });
            const vadAssetPath = typeof appUrl === 'function' ? appUrl('/static/js/vad/') : '/static/js/vad/';
            let restoreGetUserMedia = null;
            const options = {
                baseAssetPath: vadAssetPath,
                onnxWASMBasePath: vadAssetPath,
                model: 'legacy',
                redemptionFrames: 16,
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
            this._log('vad:init:ready');
            console.log('[SpeechManager] VAD ready');
        } catch (err) {
            console.warn('[SpeechManager] VAD init failed:', err);
            this._log('vad:init:error', {
                error_name: err?.name || 'unknown',
                error_message: err?.message || 'VAD init failed',
            });
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
        if (!this._transcribing) this._finalizer.speechStart();
    }

    _onVADSpeechEnd(audio) {
        this.recordEvent('vad_speech_end');
        if (this._transcribing) return;
        if (!audio || !audio.length) return;
        this._audioChunks.push(audio);
        this._finalizer.speechEnd(Math.round(audio.length / 16));
    }

    _onVADMisfire() {
        this.recordEvent('vad_misfire');
    }

    _onTurnIdlePrompt(snapshot) {
        this.recordEvent('listening_idle_prompt', snapshot);
        this._emit('listeningIdle', snapshot);
    }

    _onPostSpeechPrompt(snapshot) {
        this.recordEvent('post_speech_pause', snapshot);
        this._emit('postSpeechPause', snapshot);
    }

    _commitFinalizedAudio(snapshot = {}) {
        this._finalizationSnapshot = snapshot;
        if (this._vadReady && this._vad) this._vad.pause();
        this._transcribeAndFinish(snapshot);
    }

    _abortListening(snapshot = {}) {
        if (this._vadReady && this._vad) this._vad.pause();
        this._audioChunks = [];
        this.turnManager.reset();
        this.recordEvent('listening_aborted', snapshot);
        this._emit('listeningAborted', snapshot);
    }

    async _transcribeAndFinish(finalization = {}) {
        if (this.turnManager.getState() !== TurnState.USER_SPEAKING) return;
        if (this._audioChunks.length === 0) {
            this.turnManager.reset();
            this._emit('empty', { reason: 'no_audio', finalization });
            return;
        }
        this._transcribing = true;
        if (this._vadReady && this._vad) this._vad.pause();

        const totalLength = this._audioChunks.reduce((sum, a) => sum + a.length, 0);
        const merged = new Float32Array(totalLength);
        let off = 0;
        for (const chunk of this._audioChunks) { merged.set(chunk, off); off += chunk.length; }
        this._audioChunks = [];
        const audioDurationMs = Math.round(totalLength / 16);

        const transcribeStartedAt = performance.now();
        const baseMetadata = {
            finalization_reason: finalization.reason || 'unknown',
            finalized_by: finalization.reason || 'unknown',
            vad_segment_count: finalization.vad_segment_count,
            speech_duration_ms: finalization.speech_duration_ms,
            time_to_first_speech_ms: finalization.time_to_first_speech_ms,
            post_speech_pause_ms: finalization.post_speech_pause_ms,
            turn_elapsed_ms: finalization.turn_elapsed_ms,
            idle_prompt_count: finalization.idle_prompt_count,
            audio_duration_ms: audioDurationMs,
        };
        this.recordEvent('transcribe_started', baseMetadata);
        this._emit('transcribing', {});
        try {
            const wav = float32ToWav(merged);
            const audioBytes = wav.size || 0;
            if (audioBytes > 1024 * 1024) {
                throw new Error('audio_too_large');
            }
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
                ...baseMetadata,
                status: 'ok',
                duration_ms: Math.round(performance.now() - transcribeStartedAt),
                transcript_words: text ? text.split(/\s+/).length : 0,
                audio_bytes: audioBytes,
                transcribe_result: text ? 'transcript' : 'empty_transcript'
            });
            this.recordEvent('listening_ended', {
                ...baseMetadata,
                transcript_words: text ? text.split(/\s+/).length : 0,
                audio_bytes: audioBytes,
                transcribe_result: text ? 'transcript' : 'empty_transcript'
            });
            if (text && this.turnManager.getState() === TurnState.USER_SPEAKING) {
                this.turnManager.endUserTurn();
                this._emit('complete', { transcript: text });
            } else {
                this.turnManager.reset();
                this._emit('empty', { reason: 'empty_transcript', finalization });
            }
        } catch (err) {
            this.recordEvent('transcribe_error', {
                ...baseMetadata,
                status: 'failed',
                duration_ms: Math.round(performance.now() - transcribeStartedAt),
                error_message: err?.message || 'Transcription failed',
                transcribe_result: 'failed'
            });
            this.turnManager.reset();
            this._emit('empty', { reason: err?.message || 'transcribe_failed', finalization });
        } finally {
            this._transcribing = false;
            this._finalizer.reset();
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
        this._transcribing = false;
        this._speechDetectedCount = 0;
        this._vadFireTime = null;

        if (!this.turnManager.startUserTurn()) return false;
        this._vad.start();

        this.recordEvent('listening_started');
        this._finalizer.start();
        this._emit('listening', {});
        return true;
    }

    stopListening() {
        if (this._audioChunks.length > 0 && !this._transcribing) {
            this._finalizer.commit('manual_done');
        } else {
            this._finalizer.abort('user_cancel');
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
        this._finalizer.abort('user_cancel');
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
        this._finalizer.abort('destroy');
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
