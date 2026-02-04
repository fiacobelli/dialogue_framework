/**
 * App - Main orchestration layer
 * Wires together all modules, handles events
 */

class App {
    constructor() {
        this.micrositeUrl = '';
    }

    async init() {
        ui.init();
        this._setupTurnStateHandlers();
        this._setupSpeechHandlers();
        this._setupUIEvents();

        // Start conversation automatically
        await this.startConversation();
    }

    _setupTurnStateHandlers() {
        turnManager.on('stateChange', ({ from, to }) => {
            console.log(`Turn: ${from} -> ${to}`);
        });

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
            ui.setStatus('I didn\'t hear anything. Tap to try again.');
        });

        speechManager.on('silence', () => {
            ui.setStatus('Got it!');
        });

        speechManager.on('speakStart', () => {
            ui.showSpeaking();
        });

        speechManager.on('speakEnd', () => {
            ui.showIdle();
            ui.setStatus('');
        });

        speechManager.on('error', ({ type, message }) => {
            console.error('Speech error:', type, message);
            ui.setStatus('Error: ' + (message || type));
            turnManager.reset();
        });
    }

    _setupUIEvents() {
        // Mic button
        const micBtn = document.getElementById('micBtn');
        micBtn.addEventListener('click', () => this.toggleMic());

        // Text input
        const input = document.getElementById('input');
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendTextInput();
        });

        // Send button
        const sendBtn = document.getElementById('sendBtn');
        if (sendBtn) sendBtn.addEventListener('click', () => this.sendTextInput());

        // Photo upload
        const photoInput = document.getElementById('photoInput');
        if (photoInput) photoInput.addEventListener('change', () => this.uploadPhoto());

        // Generate button
        const generateBtn = document.getElementById('generateBtn');
        if (generateBtn) generateBtn.addEventListener('click', () => this.generate());

        // Copy link button
        const copyBtn = document.getElementById('copyLinkBtn');
        if (copyBtn) copyBtn.addEventListener('click', () => this.copyLink());
    }

    async startConversation() {
        // Default to English
        speechManager.setLanguage('en-US');
        speechManager.setVoiceConfig({ lang: 'en', gender: 'female' });

        ui.showConversation();
        ui.setStatus('Connecting...');

        try {
            const data = await conversationAPI.startSession('en', 'sitepal');
            ui.updatePhase(data.phase);
            ui.showMessage(data.prompt);
            ui.setStatus('Tap anywhere to hear greeting');

            // Play greeting on first click
            document.addEventListener('click', function playGreeting() {
                speechManager.speak(data.prompt);
                document.removeEventListener('click', playGreeting);
            }, { once: true });
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
            ui.showMessage(data.prompt);
            ui.updatePhase(data.phase);
            ui.setStatus('');
            await speechManager.speak(data.prompt);
        } catch (err) {
            ui.setStatus('Failed to send. Please try again.');
            console.error(err);
            ui.showIdle();
            turnManager.reset();
        }
    }

    async uploadPhoto() {
        const fileInput = document.getElementById('photoInput');
        const file = fileInput.files[0];
        if (!file) return;

        try {
            const data = await conversationAPI.uploadPhoto(file);
            if (data.status === 'ok') {
                ui.showPhotoSlot(data.photo_count - 1, URL.createObjectURL(file));
                if (data.ready) ui.showGenerateSection();
            }
        } catch (err) {
            ui.setStatus('Upload failed: ' + err.message);
            console.error(err);
        }
        fileInput.value = '';
    }

    async generate() {
        const name = document.getElementById('patientName').value || 'Patient';
        ui.setStatus('Generating your donor page...');

        try {
            const data = await conversationAPI.generateMicrosite(name);
            this.micrositeUrl = ui.showMicrositePreview(data);
            ui.setStatus('Done!');
        } catch (err) {
            ui.setStatus('Generation failed. Please try again.');
            console.error(err);
        }
    }

    copyLink() {
        navigator.clipboard.writeText(this.micrositeUrl).then(() => {
            const btn = document.getElementById('copyLinkBtn');
            btn.textContent = 'Copied!';
            setTimeout(() => btn.textContent = 'Copy Link', 2000);
        });
    }
}

// Create instances and wire them together
const speechManager = new SpeechManager(turnManager);
const app = new App();

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => app.init());
