/** App - Main orchestration layer for SDoH screening. */
class App {
    constructor() {
        this.conversationActive = false;
        this.patientPin = '';
        this._lastSpokenText = null;   // for repeat button
        this._turnCount = 0;           // user turns sent (drives progress bar)
        this._emptyCount = 0;          // consecutive empty VAD cycles (drives skip)
        this._maxTurns = 12;           // 6 topics + headroom
        this._inputHandler = null;
        this._paused = false;          // true when patient has paused the mic
        this._agentPaused = false;     // true when patient has paused Ludi mid-speech
    }

    async init() {
        ui.init();
        this._inputHandler = new InputHandler(this);
        this._setupTurnStateHandlers();
        this._setupSpeechHandlers();
        this._inputHandler.setupUIEvents();
        this._inputHandler.setupBeginOverlay();
    }

    _setupTurnStateHandlers() {
        turnManager.on(TurnState.IDLE,           () => ui.showIdle());
        turnManager.on(TurnState.USER_SPEAKING,  () => { ui.showListening();  ui.hideRepeatButton(); });
        turnManager.on(TurnState.PROCESSING,     () => { ui.showProcessing(); ui.hideRepeatButton(); });
        turnManager.on(TurnState.SYSTEM_SPEAKING,() => ui.showSpeaking());
    }

    _setupSpeechHandlers() {
        speechManager.on('transcript', ({ full }) => ui.showTranscript(full, false));

        speechManager.on('complete', async ({ transcript }) => {
            this._emptyCount = 0;
            ui.showTranscript(transcript, false);
            // Collect browser-side instrumentation before draining the event buffer
            speechManager.recordEvent('input_sent');
            const meta = {
                input_modality:      'voice',
                response_latency_ms: speechManager.getResponseLatency(),
                speech_confidence:   speechManager.getSpeechConfidence(),
                client_sent_at:      new Date().toISOString(),
                events:              speechManager.consumeTurnEvents(),
            };
            await this._processUserInput(transcript, meta);
        });

        speechManager.on('empty', () => {
            this._emptyCount++;
            if (this._emptyCount >= 2) {
                this._emptyCount = 0;
                this._skipCurrentQuestion();
            } else if (this.conversationActive && !this._paused) {
                speechManager.startListening();
            } else {
                ui.setStatus("I didn't hear anything.");
            }
        });

        speechManager.on('silence', () => ui.setStatus('Got it!'));

        speechManager.on('speakStart', () => ui.showSpeaking());

        speechManager.on('speakEnd', () => {
            ui.stopMessageAnimation();
            ui.setStatus('');
            if (this._agentPaused) {
                ui.showPaused();
            } else {
                if (this._lastSpokenText) ui.showRepeatButton();
                if (this.conversationActive && !this._paused) speechManager.startListening();
                else ui.showIdle();
            }
        });

        speechManager.on('recognitionEnded', () => {
            if (this.conversationActive && !this._paused && turnManager.getState() === TurnState.IDLE) {
                speechManager.startListening();
            }
        });

        speechManager.on('error', ({ type, message }) => {
            console.error('Speech error:', type, message);
            if (type !== 'no-speech' && type !== 'aborted') {
                this._speakError("I had a little trouble with that. Go ahead and try speaking again.");
            }
            turnManager.reset();
        });
    }

    _beginScreeningWithPin(pin) {
        this.patientPin = pin;
        document.getElementById('beginOverlay').style.display = 'none';
        document.getElementById('conversationUI').style.display = 'block';
        const restartRow = document.getElementById('restartRow');
        if (restartRow) restartRow.style.display = 'block';
        this.startConversation();
    }

    _restartConversation() {
        // Reset state without going back to login
        this._turnCount = 0;
        this.conversationActive = false;
        this._emptyCount = 0;
        this._paused = false;
        speechManager.destroy();
        turnManager.reset();
        ui.hideProgress();
        ui.showMessage('');
        ui.setStatus('');
        document.getElementById('thankYouScreen').style.display = 'none';
        document.getElementById('conversationUI').style.display = 'block';
        const restartRow = document.getElementById('restartRow');
        if (restartRow) restartRow.style.display = 'block';
        this.startConversation();
    }

    /** Wait for SitePal avatar to finish loading. */
    _waitForSitePal(timeoutMs = 15000) {
        if (window.sitePalReady) return Promise.resolve();
        return new Promise((resolve) => {
            const timer = setTimeout(() => {
                document.removeEventListener('sitePalReady', onReady);
                resolve();
            }, timeoutMs);
            const onReady = () => { clearTimeout(timer); resolve(); };
            document.addEventListener('sitePalReady', onReady, { once: true });
        });
    }

    async startConversation() {
        const avatarProfile = window.AVATAR_PROFILE || {};
        speechManager.setLanguage('en-US');
        speechManager.setVoiceConfig({ lang: avatarProfile.lang || 'en', gender: avatarProfile.gender || 'female' });

        ui.showConversation();
        document.getElementById('micBtn')?.classList.remove('hidden');
        ui.setStatus('Loading...');
        speechManager.initVAD();

        try {
            const avatarId = window.AVATAR_ID || 'black_female';
            const [data] = await Promise.all([
                conversationAPI.startSession('en', avatarId, this.patientPin),
                this._waitForSitePal()
            ]);
            this.conversationActive = true;
            this._paused = false;
            const preview = document.getElementById('avatarPreview');
            if (preview) {
                preview.classList.add('fade-out');
                setTimeout(() => { preview.style.display = 'none'; }, 400);
            }
            ui.showMessage(data.prompt);
            this._lastSpokenText = data.prompt;
            ui.setStatus('');
            await speechManager.speak(data.prompt);
        } catch (err) {
            console.error(err);
            this._speakError("I'm having a little trouble getting started. A staff member can help if this keeps happening.");
        }
    }

    toggleMic() {
        const state = turnManager.getState();
        console.log('[App] toggleMic state:', state, '| agentPaused:', this._agentPaused, '| paused:', this._paused);

        // Ludi is speaking → pause her
        if (state === TurnState.SYSTEM_SPEAKING) {
            this._agentPaused = true;
            ui.showPaused();
            speechManager.stopSpeaking();
            return;
        }

        // Ludi was paused mid-speech → resume (re-speak from start)
        if (this._agentPaused) {
            this._agentPaused = false;
            speechManager.speak(this._lastSpokenText);
            return;
        }

        if (state === TurnState.USER_SPEAKING) {
            speechManager.stopListening();
            return;
        }
        if (state !== TurnState.IDLE) return;

        if (this._paused) {
            this._paused = false;
            ui.showResumed();
            if (this.conversationActive) speechManager.startListening();
        } else if (this.conversationActive) {
            this._paused = true;
            speechManager.pauseListening();
            ui.showPaused();
        } else {
            speechManager.startListening();
        }
    }

    async sendTextInput() {
        const input = document.getElementById('input');
        const text = input.value.trim();
        if (!text) return;
        if (!conversationAPI.getSessionId()) { this._speakError("There's no active session. A staff member can help get this restarted."); return; }
        ui.clearTranscript();
        ui.showProcessing();
        await this._processUserInput(text, { input_modality: 'text', client_sent_at: new Date().toISOString() });
    }

    /** Re-speak the last avatar message (repeat button). */
    repeatLastMessage() {
        if (!this._lastSpokenText || turnManager.getState() !== TurnState.IDLE) return;
        ui.hideRepeatButton();
        speechManager.speak(this._lastSpokenText);
    }

    /**
     * Skip current question after repeated empty turns.
     * Sends no_response=true so the backend doesn't count it as a real turn.
     */
    async _skipCurrentQuestion() {
        if (!conversationAPI.getSessionId()) return;
        try {
            const data = await conversationAPI.sendMessage('', { no_response: true });
            this._lastSpokenText = data.prompt;
            ui.showMessage(data.prompt);
            ui.setStatus('');
            if (data.phase === 'REPORT') {
                this.conversationActive = false;
                await speechManager.speak(data.prompt);
                this.classifyAndReport();
                return;
            }
            await speechManager.speak(data.prompt);
        } catch (err) {
            console.error('Skip failed:', err);
            ui.showIdle();
        }
    }

    async _processUserInput(text, meta = {}) {
        if (!conversationAPI.getSessionId()) { ui.setStatus('No active session.'); ui.showIdle(); return; }
        ui.hideRepeatButton();
        this._lastSpokenText = '';
        ui.clearMessage();

        let phase = 'SCREENING', done = false, errored = false;

        await conversationAPI.sendMessageStream(text, meta, {
            onSentence: (sentence) => {
                ui.appendMessage(sentence);
                this._lastSpokenText += (this._lastSpokenText ? ' ' : '') + sentence;
            },
            onDone: (event) => { phase = event.phase; done = event.done; },
            onError: (message) => {
                errored = true;
                console.error('[App] Stream error:', message);
                ui.setStatus("Something went wrong. Please try again.");
                ui.showIdle();
                turnManager.reset();
            }
        });

        if (errored || !this._lastSpokenText) return;

        this._turnCount++;
        ui.showProgress(this._turnCount, this._maxTurns);

        if (done) {
            this.conversationActive = false;
            ui.showProgress(1, 1);
            await speechManager.speak(this._lastSpokenText);
            this.classifyAndReport();
        } else {
            await speechManager.speak(this._lastSpokenText);
        }
    }

    async classifyAndReport() {
        ui.setStatus('');
        const restartRow = document.getElementById('restartRow');
        if (restartRow) restartRow.style.display = 'none';
        try {
            const result = await conversationAPI.classifyResponses();
            const summary = result.verbal_summary || 'Your care team will follow up with you.';
            ui.showMessage(summary);
            await speechManager.speak(summary);
            ui.showThankYou(summary);
        } catch (err) {
            console.error('Classification failed:', err);
            ui.showThankYou();
        } finally {
            speechManager.destroy();
        }
    }

    /** Speak an error message aloud and show it in status. Patient-appropriate language only. */
    _speakError(message) {
        ui.setStatus(message);
        try { speechManager.speak(message); } catch (_) {}
    }
}

// Create instances and wire them together
const speechManager = new SpeechManager(turnManager);
const app = new App();

document.addEventListener('DOMContentLoaded', () => app.init());
