/**
 * SpeechManager - Handles speech recognition and synthesis
 * Includes silence detection for natural turn-taking
 */

class SpeechManager {
    constructor(turnManager) {
        this.turnManager = turnManager;
        this.recognition = null;
        this.synthesis = window.speechSynthesis;
        this.voices = [];
        this.transcript = '';
        this.silenceTimeout = null;
        this.silenceDelay = 2000; // 2 seconds of silence = done
        this.listeners = {};
        this.lang = 'en-US';
        this.voiceConfig = { lang: 'en', gender: 'female' };

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
        this.recognition.interimResults = true;

        this.recognition.onresult = (e) => this._handleResult(e);
        this.recognition.onerror = (e) => this._handleError(e);
        this.recognition.onend = () => this._handleEnd();
    }

    _loadVoices() {
        this.voices = this.synthesis.getVoices();
        this.synthesis.onvoiceschanged = () => {
            this.voices = this.synthesis.getVoices();
        };
    }

    _handleResult(e) {
        this._resetSilenceTimer();

        let interim = '';
        let final = '';

        for (let i = e.resultIndex; i < e.results.length; i++) {
            const text = e.results[i][0].transcript;
            if (e.results[i].isFinal) final += text + ' ';
            else interim += text;
        }

        if (final) this.transcript += final;

        this._emit('transcript', {
            final: this.transcript.trim(),
            interim: interim,
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
        if (this.turnManager.getState() === 'user_speaking') {
            this._finishListening();
        }
    }

    _resetSilenceTimer() {
        this._clearSilenceTimer();
        this.silenceTimeout = setTimeout(() => {
            this._emit('silence', { duration: this.silenceDelay });
            this._finishListening();
        }, this.silenceDelay);
    }

    _clearSilenceTimer() {
        if (this.silenceTimeout) {
            clearTimeout(this.silenceTimeout);
            this.silenceTimeout = null;
        }
    }

    _finishListening() {
        this._clearSilenceTimer();
        if (this.recognition) this.recognition.stop();

        const text = this.transcript.trim();
        if (text) {
            this.turnManager.endUserTurn();
            this._emit('complete', { transcript: text });
        } else {
            this.turnManager.reset();
            this._emit('empty', {});
        }
        this.transcript = '';
    }

    // Public API
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
        if (!this.turnManager.startUserTurn()) return false;

        this.transcript = '';
        this.recognition.lang = this.lang;
        this.recognition.start();
        this._emit('listening', {});
        return true;
    }

    stopListening() {
        this._finishListening();
    }

    speak(text) {
        if (!text) return Promise.resolve();
        if (!this.turnManager.startSystemTurn()) {
            return Promise.reject(new Error('Cannot speak now'));
        }

        this._emit('speakStart', { text });

        return new Promise((resolve) => {
            const onEnd = () => {
                document.removeEventListener('sitePalTalkEnded', onEnd);
                this.turnManager.endSystemTurn();
                this._emit('speakEnd', { text });
                resolve();
            };
            document.addEventListener('sitePalTalkEnded', onEnd);

            // Use global speakText from interview.html (handles SitePal + fallback)
            speakText(text);
        });
    }

    _selectVoice() {
        const { lang, gender } = this.voiceConfig;
        const matching = this.voices.filter(v => v.lang.startsWith(lang));
        if (matching.length === 0) return null;

        const genderPattern = gender === 'female'
            ? /female|woman|zira|eva|monica|lucia|samantha|karen/i
            : /male|man|david|jorge|pablo|daniel|alex/i;

        return matching.find(v => genderPattern.test(v.name)) || matching[0];
    }

    // Event system
    on(event, callback) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(callback);
    }

    _emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(cb => cb(data));
        }
    }
}
