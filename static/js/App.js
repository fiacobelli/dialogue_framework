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
        const lastNameInput = document.getElementById('lastNameInput');
        const dobInput = document.getElementById('dobInput');
        const beginBtn = document.getElementById('beginBtn');
        const hint = document.getElementById('pinHint');
        const micBtn = document.getElementById('micBtn');
        micBtn?.classList.add('hidden');

        this.pinHintEl = hint;

        const sanitizeName = (value) => value.trim().toLowerCase().replace(/[^a-z]/g, '');
        const extractDobDigits = (value) => value.replace(/\D/g, '').slice(0, 8);
        const formatDob = (digits) => {
            const mm = digits.slice(0, 2);
            const dd = digits.slice(2, 4);
            const yyyy = digits.slice(4, 8);
            let formatted = '';
            if (mm) formatted = mm;
            if (dd) formatted += (formatted ? '/' : '') + dd;
            if (yyyy) formatted += (formatted ? '/' : '') + yyyy;
            return formatted;
        };
        const buildPatientId = () => {
            const safeName = sanitizeName(lastNameInput.value);
            const dobDigits = extractDobDigits(dobInput.value);
            return `${safeName}-${dobDigits}`;
        };

        const validate = () => {
            const safeName = sanitizeName(lastNameInput.value);
            const dobDigits = extractDobDigits(dobInput.value);
            dobInput.value = formatDob(dobDigits);

            const validName = safeName.length >= 2;
            const validDob = dobDigits.length === 8;
            const valid = validName && validDob;
            beginBtn.disabled = !valid;
            if (!validName) hint.textContent = 'Enter at least two letters for your last name';
            else if (!validDob) hint.textContent = 'Enter date of birth as MM/DD/YYYY';
            else hint.textContent = '';
            return valid;
        };

        lastNameInput.addEventListener('input', validate);
        dobInput.addEventListener('input', (e) => {
            const digits = extractDobDigits(e.target.value);
            e.target.value = formatDob(digits);
            validate();
        });

        beginBtn.addEventListener('click', () => {
            if (validate()) {
                const patientId = buildPatientId();
                this._beginScreeningWithPin(patientId);
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
        const avatarProfile = window.AVATAR_PROFILE || {};
        speechManager.setLanguage('en-US');
        speechManager.setVoiceConfig({
            lang: avatarProfile.lang || 'en',
            gender: avatarProfile.gender || 'female'
        });

        ui.showConversation();
        document.getElementById('micBtn')?.classList.remove('hidden');
        ui.setStatus('Loading...');

        try {
            const avatarId = window.AVATAR_ID || 'black_female';
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
