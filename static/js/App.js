/** App - Main orchestration layer for SDoH screening. */
class App {
    constructor() {
        this.conversationActive = false;
        this.patientPin = '';
        this.capturingPin = false;
        this.pinPrompted = false;
        this.pinInputEl = null;
        this.pinHintEl = null;
    }

    async init() {
        ui.init();
        this._setupTurnStateHandlers();
        this._setupSpeechHandlers();
        this._setupUIEvents();

        this._setupBeginOverlay();
    }

    _setupBeginOverlay() {
        const pinInput = document.getElementById('pinInput');
        const beginBtn = document.getElementById('beginBtn');
        const hint = document.getElementById('pinHint');
        const micBtn = document.getElementById('micBtn');
        micBtn?.classList.add('hidden');

        this.pinInputEl = pinInput;
        this.pinHintEl = hint;

        const validate = () => {
            const value = pinInput.value.trim();
            const valid = value.length >= 6;
            beginBtn.disabled = !valid;
            hint.textContent = valid ? '' : 'Enter at least 6 characters';
            return valid;
        };

        pinInput.addEventListener('input', validate);

        beginBtn.addEventListener('click', () => {
            if (validate()) {
                this._beginScreeningWithPin(pinInput.value.trim());
            } else {
                this._promptForPin(pinInput, hint);
            }
        });

    }

    _beginScreeningWithPin(pin) {
        this.patientPin = pin;
        document.getElementById('beginOverlay').style.display = 'none';
        document.getElementById('conversationUI').style.display = 'block';
        this.startConversation();
    }

    _setupTurnStateHandlers() {
        turnManager.on(TurnState.IDLE, () => ui.showIdle());
        turnManager.on(TurnState.USER_SPEAKING, () => ui.showListening());
        turnManager.on(TurnState.PROCESSING, () => ui.showProcessing());
        turnManager.on(TurnState.SYSTEM_SPEAKING, () => ui.showSpeaking());
    }

    _setupSpeechHandlers() {
        speechManager.on('transcript', ({ full }) => {
            ui.showTranscript(full, true);
        });

        speechManager.on('complete', async ({ transcript }) => {
            ui.showTranscript(transcript, false);
            await this._processUserInput(transcript);
        });

        speechManager.on('empty', () => {
            if (this.conversationActive) {
                speechManager.startListening();
            } else {
                ui.setStatus('I didn\'t hear anything.');
            }
        });

        speechManager.on('silence', () => {
            ui.setStatus('Got it!');
        });

        speechManager.on('speakStart', () => {
            ui.showSpeaking();
        });

        speechManager.on('speakEnd', () => {
            ui.stopMessageAnimation();
            ui.setStatus('');
            if (this.conversationActive) {
                speechManager.startListening();
            } else {
                ui.showIdle();
            }
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

    _setupUIEvents() {
        const micBtn = document.getElementById('micBtn');
        micBtn.addEventListener('click', () => this.toggleMic());

        const input = document.getElementById('input');
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendTextInput();
        });

        const sendBtn = document.getElementById('sendBtn');
        if (sendBtn) sendBtn.addEventListener('click', () => this.sendTextInput());
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
        speechManager.setLanguage('en-US');
        speechManager.setVoiceConfig({ lang: 'en', gender: 'female' });

        ui.showConversation();
        document.getElementById('micBtn')?.classList.remove('hidden');
        ui.setStatus('Loading...');

        try {
            const urlParams = new URLSearchParams(window.location.search);
            const avatarId = urlParams.get('avatar') || 'mary';
            const [data] = await Promise.all([
                conversationAPI.startSession('en', avatarId, this.patientPin),
                this._waitForSitePal()
            ]);
            this.conversationActive = true;
            ui.showMessageAnimated(data.prompt);
            ui.setStatus('');
            await speechManager.speak(data.prompt);
        } catch (err) {
            ui.setStatus('Connection failed. Please refresh.');
            console.error(err);
        }
    }

    toggleMic() {
        const state = turnManager.getState();
        if (state === TurnState.USER_SPEAKING) {
            speechManager.stopListening();
        } else if (state === TurnState.IDLE) {
            speechManager.startListening();
        }
    }

    async sendTextInput() {
        const input = document.getElementById('input');
        const text = input.value.trim();
        if (!text) return;

        if (!conversationAPI.getSessionId()) {
            ui.setStatus('No active session. Please refresh.');
            return;
        }

        ui.clearTranscript();
        ui.showProcessing();
        await this._processUserInput(text);
    }

    async _processUserInput(text) {
        if (!conversationAPI.getSessionId()) {
            ui.setStatus('No active session.');
            ui.showIdle();
            return;
        }

        try {
            const data = await conversationAPI.sendMessage(text);
            this.conversationActive = true;
            ui.showMessageAnimated(data.prompt);
            ui.setStatus('');

            if (data.phase === 'REPORT') {
                this.conversationActive = false;
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
        ui.setStatus('Preparing your summary...');
        try {
            const result = await conversationAPI.classifyResponses();
            ui.showReport(result);
            const summary = result.verbal_summary || 'Your care team will follow up with you.';
            ui.showMessageAnimated(summary);
            await speechManager.speak(summary);
            ui.setStatus('');
        } catch (err) {
            console.error('Classification failed:', err);
            ui.setStatus('');
        }
    }
}

// Create instances and wire them together
const speechManager = new SpeechManager(turnManager);
const app = new App();

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => app.init());
