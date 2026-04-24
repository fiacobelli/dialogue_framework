/** App - Main orchestration layer for SDoH screening. */
class App {
    constructor() {
        this.conversationActive = false;
        this.patientPin = '';
        this._lastSpokenText = null;   // for repeat button
        this._turnCount = 0;           // user turns sent (drives progress bar)
        this._emptyCount = 0;          // consecutive empty VAD cycles (drives skip)
        this._maxTurns = 10;           // typical session length (~6 topics + probes)
        this._inputHandler = null;
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
            } else if (this.conversationActive) {
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
            if (this._lastSpokenText) ui.showRepeatButton();
            if (this.conversationActive) speechManager.startListening();
            else ui.showIdle();
        });

        speechManager.on('recognitionEnded', () => {
            if (this.conversationActive && turnManager.getState() === TurnState.IDLE) {
                speechManager.startListening();
            }
        });

        speechManager.on('error', ({ type, message }) => {
            console.error('Speech error:', type, message);
            ui.setStatus('Error: ' + (message || type));
            turnManager.reset();
        });
    }

    _beginScreeningWithPin(pin) {
        this.patientPin = pin;
        document.getElementById('beginOverlay').style.display = 'none';
        document.getElementById('conversationUI').style.display = 'block';
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
            ui.showMessage(data.prompt);
            this._lastSpokenText = data.prompt;
            ui.setStatus('');
            await speechManager.speak(data.prompt);
        } catch (err) {
            ui.setStatus('Connection failed. Please refresh.');
            console.error(err);
        }
    }

    toggleMic() {
        const state = turnManager.getState();
        if (state === TurnState.USER_SPEAKING) speechManager.stopListening();
        else if (state === TurnState.IDLE)     speechManager.startListening();
    }

    async sendTextInput() {
        const input = document.getElementById('input');
        const text = input.value.trim();
        if (!text) return;
        if (!conversationAPI.getSessionId()) { ui.setStatus('No active session. Please refresh.'); return; }
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
        try {
            const data = await conversationAPI.sendMessage(text, meta);
            this.conversationActive = true;
            this._turnCount++;
            ui.showMessage(data.prompt);           // instant caption — no word animation
            ui.showProgress(this._turnCount, this._maxTurns);
            this._lastSpokenText = data.prompt;
            ui.setStatus('');

            if (data.phase === 'REPORT') {
                this.conversationActive = false;
                ui.showProgress(1, 1); // snap bar to 100%
                await speechManager.speak(data.prompt);
                this.classifyAndReport();
                return;
            }
            await speechManager.speak(data.prompt);
        } catch (err) {
            ui.setStatus('Failed to send. Please try again.');
            console.error(err);
            ui.showIdle();
            turnManager.reset();
        }
    }

    async classifyAndReport() {
        ui.setStatus('');
        const restartBtn = document.getElementById('restartBtn');
        if (restartBtn) restartBtn.style.display = 'none';
        try {
            // Classification runs and saves to DB — result is for the care team, not shown to patient
            const result = await conversationAPI.classifyResponses();
            const summary = result.verbal_summary || 'Your care team will follow up with you.';
            ui.showMessage(summary);
            await speechManager.speak(summary);
            ui.showThankYou();
        } catch (err) {
            console.error('Classification failed:', err);
            ui.showThankYou();
        } finally {
            speechManager.destroy();
        }
    }
}

// Create instances and wire them together
const speechManager = new SpeechManager(turnManager);
const app = new App();

document.addEventListener('DOMContentLoaded', () => app.init());
