/**
 * App - Main orchestration layer for transplant donor-page interviews.
 */

class App {
    constructor() {
        this.micrositeUrl = '';
        this.photoPollingInterval = null;
        this.generationInProgress = false;
        this.conversationActive = false;
        this._lastSpokenText = '';
        this._emptyCount = 0;
        this._paused = false;
        this._agentPaused = false;
        this._speechActivated = false;
        this._retryCount = 0;
        this._typedStartedAt = null;
        this._typedEvents = [];
    }

    async init() {
        ui.init();
        this._setupTurnStateHandlers();
        this._setupSpeechHandlers();
        this._setupUIEvents();
        await this.startConversation();
    }

    _setupTurnStateHandlers() {
        turnManager.on('stateChange', ({ from, to }) => {
            console.log(`Turn: ${from} -> ${to}`);
        });

        turnManager.on(TurnState.IDLE, () => {
            if (!this._agentPaused && !this._paused) ui.showIdle();
        });
        turnManager.on(TurnState.USER_SPEAKING, () => {
            ui.showListening();
            ui.hideRepeatButton();
        });
        turnManager.on(TurnState.PROCESSING, () => {
            ui.showProcessing();
            ui.hideRepeatButton();
        });
        turnManager.on(TurnState.SYSTEM_SPEAKING, () => ui.showSpeaking());
    }

    _setupSpeechHandlers() {
        speechManager.on('transcript', ({ full }) => ui.showTranscript(full, false));

        speechManager.on('complete', async ({ transcript }) => {
            this._emptyCount = 0;
            ui.showTranscript(transcript, false);
            await this._processUserInput(transcript, 'voice');
        });

        speechManager.on('empty', async () => {
            this._emptyCount++;
            this._retryCount++;
            if (this.conversationActive && !this._paused && this._emptyCount < 2) {
                speechManager.startListening();
            } else {
                this._emptyCount = 0;
                await this._processNoResponse();
            }
        });

        speechManager.on('silence', () => ui.setStatus('Got it!'));

        speechManager.on('speakStart', ({ text }) => {
            ui.showSpeaking();
            if (text) ui.showMessageAnimated(text);
        });

        speechManager.on('speakEnd', () => {
            ui.stopMessageAnimation();
            ui.setStatus('');
            if (this._agentPaused) {
                ui.showPaused();
            } else {
                if (this._lastSpokenText) ui.showRepeatButton();
                if (this.conversationActive && !this._paused) {
                    speechManager.startListening();
                } else {
                    ui.showIdle();
                }
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
                ui.setStatus(message || "I had a little trouble with the microphone. You can try again or type your answer.");
            }
            turnManager.reset();
        });
    }

    _setupUIEvents() {
        const micBtn = document.getElementById('micBtn');
        if (micBtn) micBtn.addEventListener('click', () => this.toggleMic());

        const input = document.getElementById('input');
        if (input) {
            input.addEventListener('input', () => this._markTypedStarted(input.value));
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.sendTextInput();
            });
        }

        const sendBtn = document.getElementById('sendBtn');
        if (sendBtn) sendBtn.addEventListener('click', () => this.sendTextInput());

        const photoInput = document.getElementById('photoInput');
        if (photoInput) photoInput.addEventListener('change', () => this.uploadPhoto());

        const generateBtn = document.getElementById('generateBtn');
        if (generateBtn) generateBtn.addEventListener('click', () => this.generate());

        const publishBtn = document.getElementById('publishBtn');
        if (publishBtn) publishBtn.addEventListener('click', () => this.publish());

        const copyBtn = document.getElementById('copyLinkBtn');
        if (copyBtn) copyBtn.addEventListener('click', () => this.copyLink());

        const repeatBtn = document.getElementById('repeatBtn');
        if (repeatBtn) repeatBtn.addEventListener('click', () => {
            speechManager.recordEvent('repeat_clicked');
            this.repeatLastMessage();
        });

        const beginBtn = document.getElementById('beginBtn');
        if (beginBtn) beginBtn.addEventListener('click', () => this.beginInterview());
    }

    _waitForSitePal(timeoutMs = 15000) {
        if (window.sitePalReady) return Promise.resolve();
        return new Promise((resolve) => {
            const timer = setTimeout(() => {
                document.removeEventListener('sitePalReady', onReady);
                resolve();
            }, timeoutMs);
            const onReady = () => {
                clearTimeout(timer);
                resolve();
            };
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
        ui.setStatus('Loading...');

        try {
            const urlParams = new URLSearchParams(window.location.search);
            const avatarId = window.AVATAR_ID || urlParams.get('avatar') || 'black_female';
            const [data] = await Promise.all([
                conversationAPI.startSession('en', avatarId),
                this._waitForSitePal()
            ]);

            this.conversationActive = false;
            this._paused = false;
            this._lastSpokenText = data.prompt;
            ui.showMessage(data.prompt);
            ui.showBeginOverlay();
            ui.setStatus('');

            const preview = document.getElementById('avatarPreview');
            if (preview) {
                preview.classList.add('fade-out');
                setTimeout(() => { preview.style.display = 'none'; }, 400);
            }
        } catch (err) {
            ui.setStatus('Connection failed. Please refresh.');
            console.error(err);
        }
    }

    async beginInterview() {
        if (this._speechActivated) return;
        this._speechActivated = true;
        ui.setBeginLoading(true);
        ui.showConversation();
        ui.setStatus('Preparing microphone...');

        try {
            await speechManager.initVAD();
            this.conversationActive = true;
            this._paused = false;
            ui.setStatus('');
            await speechManager.speak(this._lastSpokenText);
        } catch (err) {
            console.error('Failed to begin interview:', err);
            this._speechActivated = false;
            this.conversationActive = false;
            ui.showBeginOverlay();
            ui.setBeginLoading(false);
            ui.setStatus('Could not start audio. You can try again or type your answer.');
        }
    }

    toggleMic() {
        const state = turnManager.getState();

        if (!this._speechActivated && this.conversationActive) {
            this.beginInterview();
            return;
        }

        if (state === TurnState.SYSTEM_SPEAKING) {
            this._agentPaused = true;
            speechManager.recordEvent('pause_clicked');
            ui.showPaused();
            speechManager.stopSpeaking();
            return;
        }

        if (this._agentPaused) {
            this._agentPaused = false;
            speechManager.recordEvent('resume_clicked');
            speechManager.speak(this._lastSpokenText);
            return;
        }

        if (state === TurnState.USER_SPEAKING) {
            if (speechManager._vadReady) {
                speechManager.stopListening();
            } else {
                this._paused = true;
                speechManager.pauseListening();
                ui.showPaused();
            }
            return;
        }

        if (state !== TurnState.IDLE) return;

        if (this._paused) {
            this._paused = false;
            speechManager.recordEvent('resume_clicked');
            ui.showResumed();
            if (this.conversationActive) speechManager.startListening();
        } else if (this.conversationActive) {
            this._paused = true;
            speechManager.recordEvent('pause_clicked');
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

        if (!conversationAPI.getSessionId()) {
            ui.setStatus('No active session. Please refresh.');
            return;
        }

        ui.clearTranscript();
        ui.showProcessing();
        this._markTypedSent();
        await this._processUserInput(text, 'typed');
    }

    _markTypedStarted(value) {
        if (!value || this._typedStartedAt !== null) return;
        this._typedStartedAt = performance.now();
        this._typedEvents.push({ type: 'typed_started', ts: Math.round(this._typedStartedAt) });
    }

    _markTypedSent() {
        const now = performance.now();
        if (this._typedStartedAt === null) {
            this._typedStartedAt = now;
            this._typedEvents.push({ type: 'typed_started', ts: Math.round(now) });
        }
        this._typedEvents.push({ type: 'typed_sent', ts: Math.round(now) });
    }

    _durationBetween(events, startType, endType) {
        const start = [...events].reverse().find(e => e.type === startType);
        const end = [...events].reverse().find(e => e.type === endType);
        if (!start || !end) return null;
        return Math.max(0, Math.round(end.ts - start.ts));
    }

    _buildTurnMetadata(inputModality) {
        const speechEvents = speechManager.consumeTurnEvents();
        const typedEvents = this._typedEvents.slice();
        const events = [...speechEvents, ...typedEvents];
        const typedStarted = typedEvents.find(e => e.type === 'typed_started');
        const typedSent = [...typedEvents].reverse().find(e => e.type === 'typed_sent');
        const speakEnd = speechManager.getLastSpeakEndTime();
        let responseLatency = inputModality === 'voice'
            ? speechManager.getResponseLatency()
            : null;
        let answerDuration = inputModality === 'voice'
            ? this._durationBetween(events, 'recognition_started', 'recognition_ended')
            : null;

        if (inputModality === 'typed' && typedSent) {
            const responsePoint = typedStarted || typedSent;
            responseLatency = speakEnd === null ? null : Math.max(0, Math.round(responsePoint.ts - speakEnd));
            answerDuration = typedStarted ? Math.max(0, Math.round(typedSent.ts - typedStarted.ts)) : 0;
        }

        const metadata = {
            input_modality: inputModality,
            response_latency_ms: responseLatency,
            answer_duration_ms: answerDuration,
            speech_confidence: inputModality === 'voice' ? speechManager.getSpeechConfidence() : null,
            client_sent_at: new Date().toISOString(),
            retry_count: this._retryCount,
            tts_duration_ms: speechManager.getLastTtsDuration(),
            events
        };

        this._retryCount = 0;
        this._typedStartedAt = null;
        this._typedEvents = [];
        return metadata;
    }

    async _processUserInput(text, inputModality = 'unknown') {
        if (!conversationAPI.getSessionId()) {
            ui.setStatus('No active session.');
            ui.showIdle();
            return;
        }

        try {
            ui.hideRepeatButton();
            this._lastSpokenText = '';
            ui.clearMessage();

            const data = await conversationAPI.sendMessage(text, this._buildTurnMetadata(inputModality));
            this._lastSpokenText = data.prompt;
            ui.showMessage(data.prompt);
            ui.setStatus('');

            if (data.phase === 'PHOTOS') {
                this.conversationActive = false;
                await speechManager.speak(data.prompt);
                this.startPhotoFlow();
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

    async _processNoResponse() {
        if (!conversationAPI.getSessionId()) {
            ui.setStatus("I didn't hear anything. You can try speaking again or type your answer.");
            ui.showIdle();
            return;
        }

        try {
            ui.hideRepeatButton();
            ui.showProcessing();
            const metadata = this._buildTurnMetadata('voice');
            const data = await conversationAPI.sendNoResponse(metadata);
            this._lastSpokenText = data.prompt;
            ui.showMessage(data.prompt);
            ui.setStatus('');
            await speechManager.speak(data.prompt);
        } catch (err) {
            console.error('Failed to send no-response turn:', err);
            ui.setStatus("I didn't hear anything. You can try speaking again or type your answer.");
            ui.showIdle();
            turnManager.reset();
        }
    }

    async startPhotoFlow() {
        ui.updatePhase('PHOTOS');
        speechManager.destroy();

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
            const data = await conversationAPI.uploadPhoto(file, 'desktop');
            if (data.status === 'ok') {
                ui.showPhotoSlot(data.photo_count - 1, URL.createObjectURL(file));
                if (data.ready) {
                    this.stopPhotoPolling();
                    this.autoGenerate();
                }
            }
        } catch (err) {
            ui.setStatus(`Upload failed: ${err.message}`);
            console.error(err);
        }
        fileInput.value = '';
    }

    async autoGenerate() {
        if (this.generationInProgress) return;
        this.generationInProgress = true;
        ui.showGenerating();

        try {
            const data = await conversationAPI.generateMicrosite('Patient');
            ui.showDraftReview(data);
            ui.setStatus('Review your draft, then publish when it looks right.');
            this._lastSpokenText = `I drafted your donor page, ${data.name}. Please review it before publishing.`;
        } catch (err) {
            console.error('Auto-generation failed:', err);
            ui.showGenerateSection();
            ui.setStatus('Generation failed. Please try again.');
        } finally {
            this.generationInProgress = false;
        }
    }

    async generate() {
        const name = document.getElementById('patientName').value || 'Patient';
        ui.setStatus('Generating your donor page...');

        try {
            const data = await conversationAPI.generateMicrosite(name);
            ui.showDraftReview(data);
            ui.setStatus('Review your draft, then publish when it looks right.');
        } catch (err) {
            ui.setStatus('Generation failed. Please try again.');
            console.error(err);
        }
    }

    async publish() {
        ui.showPublishing();

        try {
            const data = await conversationAPI.publishMicrosite(ui.getDraftReviewEdits());
            const fullUrl = data.microsite_absolute_url || absoluteAppUrl(data.microsite_url);
            this.micrositeUrl = fullUrl;
            ui.showPublished();
            ui.showCelebration(fullUrl);
            ui.showMicrositePreview(data);
            ui.setStatus('Published.');
        } catch (err) {
            ui.setStatus('Publish failed. Please try again.');
            console.error(err);
            const btn = document.getElementById('publishBtn');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Publish My Donor Page';
            }
        }
    }

    copyLink() {
        navigator.clipboard.writeText(this.micrositeUrl).then(() => {
            const btn = document.getElementById('copyLinkBtn');
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = 'Copy Link'; }, 2000);
        });
    }

    repeatLastMessage() {
        if (!this._lastSpokenText || turnManager.getState() !== TurnState.IDLE) return;
        ui.hideRepeatButton();
        speechManager.speak(this._lastSpokenText).catch((err) => {
            console.error('Repeat failed:', err);
            ui.showIdle();
        });
    }
}

const speechManager = new SpeechManager(turnManager);
const app = new App();

document.addEventListener('DOMContentLoaded', () => app.init());
