/**
 * App - Main orchestration layer
 * Wires together all modules, handles events
 */

class App {
    constructor() {
        this.micrositeUrl = '';
        this.photoPollingInterval = null;
        this.generationInProgress = false;
    }

    /** Initialize app and start conversation. */
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
            ui.stopMessageAnimation();
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
            const urlParams = new URLSearchParams(window.location.search);
            const avatarId = urlParams.get('avatar') || 'mary';
            const data = await conversationAPI.startSession('en', avatarId);
            ui.updatePhase(data.phase);
            ui.showMessageAnimated(data.prompt);
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

    /** Toggle microphone on/off based on current turn state. */
    toggleMic() {
        const state = turnManager.getState();
        if (state === TurnState.USER_SPEAKING) {
            speechManager.stopListening();
        } else if (state === TurnState.IDLE) {
            speechManager.startListening();
        }
    }

    /** Send text input to backend and process response. */
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

    /** Process user input through the dialogue system. */
    async _processUserInput(text) {
        if (!conversationAPI.getSessionId()) {
            ui.setStatus('No active session.');
            ui.showIdle();
            return;
        }

        try {
            const data = await conversationAPI.sendMessage(text);
            ui.showMessageAnimated(data.prompt);
            ui.updatePhase(data.phase);
            ui.setStatus('');

            // Start QR/photo flow when entering PHOTOS phase
            if (data.phase === 'PHOTOS') {
                this.startPhotoFlow();
            }

            await speechManager.speak(data.prompt);
        } catch (err) {
            ui.setStatus('Failed to send. Please try again.');
            console.error(err);
            ui.showIdle();
            turnManager.reset();
        }
    }

    /** Start QR code display and photo polling. */
    async startPhotoFlow() {
        try {
            const qrData = await conversationAPI.getQRCode();
            ui.setQRCode(qrData.qr_image, qrData.upload_url);
            this.startPhotoPolling();
        } catch (err) {
            console.error('Failed to get QR code:', err);
        }
    }

    startPhotoPolling() {
        if (this.photoPollingInterval) return;

        this.photoPollingInterval = setInterval(async () => {
            try {
                const status = await conversationAPI.getPhotoStatus();
                ui.updatePhotoProgress(status.photo_count, status.max_photos);

                if (status.ready) {
                    this.stopPhotoPolling();
                    this.autoGenerate();
                }
            } catch (err) {
                console.error('Photo polling error:', err);
            }
        }, 3000);
    }

    stopPhotoPolling() {
        if (this.photoPollingInterval) {
            clearInterval(this.photoPollingInterval);
            this.photoPollingInterval = null;
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
                if (data.ready) {
                    this.stopPhotoPolling();
                    this.autoGenerate();
                }
            }
        } catch (err) {
            ui.setStatus('Upload failed: ' + err.message);
            console.error(err);
        }
        fileInput.value = '';
    }

    /** Auto-generate microsite after photos are uploaded. */
    async autoGenerate() {
        if (this.generationInProgress) return;
        this.generationInProgress = true;
        ui.showGenerating();

        try {
            const data = await conversationAPI.generateMicrosite('Patient');

            const fullUrl = data.microsite_absolute_url || absoluteAppUrl(data.microsite_url);
            this.micrositeUrl = fullUrl;

            // Avatar celebration message
            const message = `Wonderful news, ${data.name}! Your donor page is ready! Click the button below to see it and share it with your loved ones.`;
            ui.showMessageAnimated(message);
            ui.showCelebration(fullUrl);

            // Use speechManager for proper turn handling (returns Promise)
            await speechManager.speak(message);
            ui.setStatus('');
        } catch (err) {
            console.error('Auto-generation failed:', err);
            ui.showGenerateSection();
            ui.setStatus('Generation failed. Please try again.');
        } finally {
            // Always reset flag
            this.generationInProgress = false;
        }
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
