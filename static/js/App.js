/**
 * App - Main orchestration layer for transplant donor-page interviews.
 */

class App {
    constructor() {
        this.micrositeUrl = '';
        this.photoPollingInterval = null;
        this.photoPollingErrors = 0;
        this.lastPhotoCount = 0;
        this.pendingPhotoReplaceFilename = '';
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
        this._startupReady = false;
        this._startupInProgress = false;
        this._startupStartedAt = null;
        this._startupTimeoutHandle = null;
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

        speechManager.on('empty', async ({ reason } = {}) => {
            this._emptyCount++;
            this._retryCount++;
            if (reason === 'user_cancel') {
                ui.showPaused();
                return;
            }
            if (this.conversationActive && !this._paused && this._emptyCount < 2 && reason !== 'audio_too_large') {
                ui.setStatus("I didn't catch that clearly. I'll keep listening; you can also type your answer.");
                speechManager.startListening();
            } else {
                this._emptyCount = 0;
                const message = reason === 'audio_too_large'
                    ? 'That answer was longer than this recorder can send at once. Please try again in a shorter response, or type your answer.'
                    : "I didn't catch that clearly. Please try speaking again, or type your answer.";
                ui.setStatus(message);
                ui.showIdle();
            }
        });

        speechManager.on('listeningIdle', () => {
            ui.showListeningIdle();
            ui.setStatus('Still listening. Take your time.');
        });

        speechManager.on('postSpeechPause', () => {
            ui.showPostSpeechPause();
            ui.setStatus('I am listening in case you want to add more.');
        });

        speechManager.on('listeningAborted', ({ reason } = {}) => {
            if (reason === 'max_turn') {
                ui.setStatus('I paused listening so the microphone would not stay open too long. Tap the mic or type below when ready.');
            }
            ui.showIdle();
        });

        speechManager.on('transcribing', () => {
            ui.showTranscribing();
        });

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

        const skipQuestionBtn = document.getElementById('skipQuestionBtn');
        if (skipQuestionBtn) skipQuestionBtn.addEventListener('click', () => this.skipCurrentQuestion());

        const photoInput = document.getElementById('photoInput');
        if (photoInput) photoInput.addEventListener('change', () => this.uploadPhoto());
        document.querySelectorAll('.photo-section .photo-slot').forEach(slot => {
            slot.addEventListener('click', (e) => {
                this.pendingPhotoReplaceFilename = slot.dataset.filename || '';
                photoInput?.click();
            });
            slot.addEventListener('keydown', (e) => {
                if (!['Enter', ' '].includes(e.key)) return;
                e.preventDefault();
                this.pendingPhotoReplaceFilename = slot.dataset.filename || '';
                photoInput?.click();
            });
        });

        const generateBtn = document.getElementById('generateBtn');
        if (generateBtn) generateBtn.addEventListener('click', () => this.generate());

        const continueWithPhotosBtn = document.getElementById('continueWithPhotosBtn');
        if (continueWithPhotosBtn) {
            continueWithPhotosBtn.addEventListener('click', () => this.continueWithPartialPhotos());
        }

        const publishBtn = document.getElementById('publishBtn');
        if (publishBtn) publishBtn.addEventListener('click', () => this.publish());

        const copyBtn = document.getElementById('copyLinkBtn');
        if (copyBtn) copyBtn.addEventListener('click', () => this.copyLink());

        const unpublishBtn = document.getElementById('unpublishBtn');
        if (unpublishBtn) unpublishBtn.addEventListener('click', () => this.unpublish());

        const repeatBtn = document.getElementById('repeatBtn');
        if (repeatBtn) repeatBtn.addEventListener('click', () => {
            speechManager.recordEvent('repeat_clicked');
            this.repeatLastMessage();
        });

        const beginBtn = document.getElementById('beginBtn');
        if (beginBtn) beginBtn.addEventListener('click', () => {
            if (!this._startupReady) {
                this.startConversation();
                return;
            }
            this.beginInterview();
        });
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
        if (this._startupInProgress) return;
        this._startupInProgress = true;
        this._startupReady = false;
        const avatarProfile = window.AVATAR_PROFILE || {};
        speechManager.setLanguage('en-US');
        speechManager.setVoiceConfig({
            lang: avatarProfile.lang || 'en',
            gender: avatarProfile.gender || 'female'
        });

        ui.hideConversation();
        ui.showBeginOverlay();
        ui.setBeginLoading(true, 'Loading Ludi...');
        ui.showMicPreflight('checking', 'Getting Ludi ready...', 'Connecting to your interview session and avatar.');
        ui.setStatus('Loading...');
        this._startupStartedAt = performance.now();

        try {
            const urlParams = new URLSearchParams(window.location.search);
            const avatarId = window.AVATAR_ID || urlParams.get('avatar') || 'black_female';
            const startupTimeoutMs = 25000;
            const [data] = await Promise.all([
                conversationAPI.startSession('en', avatarId, startupTimeoutMs),
                this._waitForSitePal()
            ]);
            const elapsedMs = this._startupStartedAt === null ? null : Math.max(0, Math.round(performance.now() - this._startupStartedAt));
            console.info('[microsite] startup ready', { elapsedMs, avatarId });

            this.conversationActive = false;
            this._paused = false;
            this._lastSpokenText = data.prompt;
            this._startupReady = true;
            ui.updateProgress(data.progress);
            ui.clearMessage();
            ui.showMicPreflight('ready', 'Ludi is ready.', 'Tap begin interview when you are ready.');
            ui.setBeginLoading(false, 'Begin interview');
            ui.showBeginOverlay();
            ui.setStatus('');

            const preview = document.getElementById('avatarPreview');
            if (preview) {
                preview.classList.add('fade-out');
                setTimeout(() => { preview.style.display = 'none'; }, 400);
            }
        } catch (err) {
            const elapsedMs = this._startupStartedAt === null ? null : Math.max(0, Math.round(performance.now() - this._startupStartedAt));
            console.warn('[microsite] startup failed', { elapsedMs, error: err?.message || String(err) });
            this._startupReady = false;
            ui.setBeginLoading(false, 'Retry loading Ludi');
            ui.showMicPreflight(
                'error',
                'Could not load Ludi.',
                err?.message === 'Session loading timed out.'
                    ? 'The server took too long to respond. Check the connection and tap retry.'
                    : 'Check the connection and tap retry.'
            );
            ui.setStatus('');
            console.error(err);
        } finally {
            this._startupInProgress = false;
            this._startupStartedAt = null;
            if (this._startupTimeoutHandle) {
                clearTimeout(this._startupTimeoutHandle);
                this._startupTimeoutHandle = null;
            }
        }
    }

    async beginInterview() {
        if (!this._startupReady) {
            await this.startConversation();
            return;
        }
        if (this._speechActivated) return;
        this._speechActivated = true;
        ui.setBeginLoading(true, 'Checking microphone...');
        ui.clearMessage();
        ui.setStatus('');
        ui.showMicPreflight('checking', 'Checking microphone...', 'Please allow microphone access if your browser asks.');

        try {
            await this._recordClientEvents([{ type: 'mic_preflight_started', ts: Math.round(performance.now()) }]);
            const preflight = await speechManager.preflightMicrophone();
            await this._recordClientEvents([{
                type: 'mic_preflight_result',
                ts: Math.round(performance.now()),
                metadata: preflight.metadata
            }]);

            if (!preflight.ok) {
                throw this._microphonePreflightError(preflight.metadata);
            }

            ui.showMicPreflight('ready', 'Microphone ready.', this._microphoneReadyDetail(preflight.metadata));
            await speechManager.initVAD(preflight.stream);
            this.conversationActive = true;
            this._paused = false;
            ui.showConversation();
            ui.setStatus('');
            await speechManager.speak(this._lastSpokenText);
        } catch (err) {
            console.error('Failed to begin interview:', err);
            this._speechActivated = false;
            this.conversationActive = false;
            ui.showBeginOverlay();
            ui.setBeginLoading(false);
            ui.showMicPreflight(
                'error',
                err.userMessage || 'Microphone is not ready.',
                err.userDetail || 'You can fix microphone access and try again, or type your answers after starting.'
            );
            ui.setStatus('');
        }
    }

    async _recordClientEvents(events) {
        try {
            await conversationAPI.sendClientEvents(events);
        } catch (err) {
            console.warn('Failed to save client diagnostics:', err);
        }
    }

    _microphoneReadyDetail(metadata = {}) {
        const parts = [];
        if (metadata.active_track_label) parts.push(`Using: ${metadata.active_track_label}`);
        if (metadata.audioinput_count !== undefined) parts.push(`${metadata.audioinput_count} audio input(s) found`);
        if (metadata.bluetooth_input_detected) parts.push('Bluetooth input detected');
        return parts.join(' · ');
    }

    _microphonePreflightError(metadata = {}) {
        const err = new Error(metadata.status || 'microphone_preflight_failed');
        const name = metadata.error_name || metadata.status || 'microphone_preflight_failed';
        const messages = {
            insecure_context: [
                'Microphone requires the secure site.',
                'Open the HTTPS version of the page, then try again.'
            ],
            speech_recognition_unsupported: [
                'Speech recognition is not supported in this browser.',
                'Use Chrome on the tablet, or type answers instead.'
            ],
            get_user_media_unsupported: [
                'This browser cannot request microphone access.',
                'Use Chrome on the tablet, or type answers instead.'
            ],
            no_live_audio_track: [
                'No active microphone was detected.',
                'Check that the tablet or Bluetooth microphone is connected, then try again.'
            ],
            failed: [
                name === 'NotAllowedError' ? 'Microphone permission is blocked.' : 'Microphone check failed.',
                name === 'NotAllowedError'
                    ? 'Allow microphone access for this site in the browser settings, then try again.'
                    : (metadata.error_message || 'Check the microphone connection and try again.')
            ]
        };
        const [userMessage, userDetail] = messages[metadata.status] || messages.failed;
        err.userMessage = userMessage;
        err.userDetail = userDetail;
        return err;
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

    async skipCurrentQuestion() {
        if (!this.conversationActive || !conversationAPI.getSessionId()) return;
        if (!window.confirm('Skip this question and move to the next part of your story?')) return;

        speechManager.recordEvent('skip_clicked');
        ui.clearTranscript();
        ui.showProcessing();
        await this._processUserInput('[skip]', 'typed', { skip_requested: true });
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

    _buildTurnMetadata(inputModality, extra = {}) {
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
            ? this._durationBetween(events, 'listening_started', 'listening_ended')
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
            events,
            ...extra
        };

        this._retryCount = 0;
        this._typedStartedAt = null;
        this._typedEvents = [];
        return metadata;
    }

    async _processUserInput(text, inputModality = 'unknown', metadataExtra = {}) {
        if (!conversationAPI.getSessionId()) {
            ui.setStatus('No active session.');
            ui.showIdle();
            return;
        }

        try {
            ui.hideRepeatButton();
            this._lastSpokenText = '';
            ui.clearMessage();

            const data = await conversationAPI.sendMessage(text, this._buildTurnMetadata(inputModality, metadataExtra));
            this._lastSpokenText = data.prompt;
            ui.updateProgress(data.progress);
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

    async startPhotoFlow() {
        ui.updatePhase('PHOTOS');
        speechManager.destroy();

        try {
            const qrData = await conversationAPI.getQRCode();
            ui.setQRCode(qrData.qr_image, qrData.upload_url);
            ui.updatePhotoProgress(0, 3);
            ui.setPhotoStatus('Scan the QR code with your phone, or upload photos from this device. This page will update automatically.', 'info');
            this.startPhotoPolling();
        } catch (err) {
            console.error('Failed to get QR code:', err);
            ui.setPhotoStatus('Could not create the phone upload link. You can still upload photos from this device.', 'error');
        }
    }

    startPhotoPolling() {
        if (this.photoPollingInterval) return;
        this.photoPollingErrors = 0;

        this.photoPollingInterval = setInterval(async () => {
            try {
                const status = await conversationAPI.getPhotoStatus();
                this.photoPollingErrors = 0;
                ui.updatePhotoProgress(status.photo_count, status.max_photos);
                const photoItems = status.photo_items || (status.photos || []).map((url) => ({ url }));
                photoItems.forEach((item, index) => ui.showPhotoSlot(index, item));

                if (status.ready) {
                    this.stopPhotoPolling();
                    ui.showGenerateSection();
                    ui.setPhotoStatus('All photos are received. Review each photo slot, then draft the donor page.', 'success');
                    ui.setStatus('Review the photo slots, then draft your donor page.');
                } else if ((status.photo_count || 0) > this.lastPhotoCount) {
                    ui.setPhotoStatus(`${status.photo_count} photo${status.photo_count === 1 ? '' : 's'} received. You can add more or continue with fewer.`, 'success');
                } else if ((status.photo_count || 0) === 0) {
                    ui.setPhotoStatus('Waiting for photos. If you uploaded from your phone, keep this desktop page open.', 'info');
                } else {
                    ui.setPhotoStatus(`${status.photo_count} photo${status.photo_count === 1 ? '' : 's'} received. Add more photos or continue with the uploaded photos.`, 'info');
                }
                this.lastPhotoCount = status.photo_count || 0;
            } catch (err) {
                console.error('Photo polling error:', err);
                this.photoPollingErrors += 1;
                if (this.photoPollingErrors >= 3) {
                    ui.setPhotoStatus('I cannot check for new phone uploads right now. You can still upload from this device, or refresh the page if needed.', 'error');
                } else {
                    ui.setPhotoStatus('Still checking for phone uploads...', 'info');
                }
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
        const files = Array.from(fileInput.files || []);
        if (!files.length) return;
        const replaceFilename = this.pendingPhotoReplaceFilename;
        const selectedFiles = replaceFilename ? files.slice(0, 1) : files;

        try {
            let latest = null;
            for (const [index, file] of selectedFiles.entries()) {
                const action = replaceFilename ? 'Replacing photo' : `Uploading photo ${index + 1} of ${selectedFiles.length}`;
                ui.setPhotoStatus(`${action}...`, 'info');
                latest = await conversationAPI.uploadPhoto(file, 'desktop', { replaceFilename });
                if (latest.status === 'ok') {
                    const photoItems = latest.photo_items || [];
                    if (photoItems.length) {
                        photoItems.forEach((item, index) => ui.showPhotoSlot(index, item));
                    } else {
                        ui.showPhotoSlot(latest.photo_count - 1, URL.createObjectURL(file));
                    }
                    ui.updatePhotoProgress(latest.photo_count, latest.max_photos || 3);
                }
                if (latest.ready) break;
            }
            if (latest?.ready) {
                this.stopPhotoPolling();
                ui.showGenerateSection();
                ui.setPhotoStatus('All photos are received. Review each photo slot, then draft the donor page.', 'success');
                ui.setStatus('Review the photo slots, then draft your donor page.');
            } else if (latest?.replaced) {
                ui.setPhotoStatus('Photo replaced. Review the photo slots before drafting the donor page.', 'success');
            } else if (latest?.photo_count) {
                ui.setPhotoStatus(`${latest.photo_count} photo${latest.photo_count === 1 ? '' : 's'} received. Add more photos or continue with the uploaded photos.`, 'success');
            }
        } catch (err) {
            ui.setPhotoStatus(`Upload failed: ${err.message}`, 'error');
            ui.setStatus(`Upload failed: ${err.message}`);
            console.error(err);
        }
        fileInput.value = '';
        this.pendingPhotoReplaceFilename = '';
    }

    collectPhotoMetadata() {
        return Array.from(document.querySelectorAll('.photo-section .photo-slot.filled'))
            .map((slot, index) => ({
                stored_filename: slot.dataset.filename,
                photo_role: slot.dataset.role || ['before', 'during', 'hope'][index] || 'general',
                display_order: index
            }))
            .filter(item => item.stored_filename);
    }

    async savePhotoMetadata() {
        const photos = this.collectPhotoMetadata();
        if (!photos.length) return null;
        try {
            const data = await conversationAPI.updatePhotoMetadata(photos);
            const photoItems = data.photo_items || [];
            photoItems.forEach((item, index) => ui.showPhotoSlot(index, item));
            return data;
        } catch (err) {
            ui.setStatus(`Could not save photo details: ${err.message}`);
            console.error(err);
            return null;
        }
    }

    async autoGenerate() {
        if (this.generationInProgress) return;
        this.generationInProgress = true;
        ui.showGenerating();

        try {
            await this.savePhotoMetadata();
            const data = await conversationAPI.generateMicrosite('');
            ui.showDraftReview(data);
            ui.setStatus('Review your draft, then publish when it looks right.');
            this._lastSpokenText = `I drafted your donor page, ${data.name}. Please review it before publishing.`;
        } catch (err) {
            console.error('Auto-generation failed:', err);
            ui.showGenerateSection();
            ui.setStatus(this._generationErrorMessage(err));
        } finally {
            this.generationInProgress = false;
        }
    }

    async continueWithPartialPhotos() {
        const status = await conversationAPI.getPhotoStatus();
        const count = status.photo_count || 0;
        if (count <= 0) {
            ui.setStatus('Please upload at least one photo before continuing.');
            return;
        }
        if (count >= (status.max_photos || 3)) {
            await this.generate(false);
            return;
        }

        const ok = window.confirm(
            `You uploaded ${count} photo${count === 1 ? '' : 's'}. Three photos are recommended, but you can continue with fewer. Continue now?`
        );
        if (!ok) return;

        this.stopPhotoPolling();
        await this.generate(true);
    }

    async generate(allowPartialPhotos = false) {
        if (this.generationInProgress) return;
        this.generationInProgress = true;
        const name = document.getElementById('patientName').value || 'Patient';
        ui.showGenerating();
        ui.setStatus(allowPartialPhotos
            ? 'Generating your donor page with the photos uploaded so far...'
            : 'Generating your donor page...');

        try {
            await this.savePhotoMetadata();
            const data = await conversationAPI.generateMicrosite(name, { allowPartialPhotos });
            ui.showDraftReview(data);
            ui.setStatus('Review your draft, then publish when it looks right.');
        } catch (err) {
            const message = this._generationErrorMessage(err);
            ui.showGenerateSection();
            ui.setStatus(message);
            ui.setPhotoStatus(message, 'error');
            console.error(err);
        } finally {
            this.generationInProgress = false;
        }
    }

    async publish() {
        const consent = ui.getPublicationConsent();
        if (!consent.accepted) {
            ui.setStatus('Please confirm that you understand this page may become public before publishing.');
            return;
        }
        ui.showPublishing();

        try {
            const data = await conversationAPI.publishMicrosite(ui.getDraftReviewEdits(), consent);
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

    _generationErrorMessage(err) {
        const detail = err?.detail || {};
        if (detail.error === 'generation_not_ready' && Array.isArray(detail.missing_story_sections)) {
            const sections = detail.missing_story_sections.join(', ');
            return sections
                ? `I need one more detail before I can draft the page. Missing section: ${sections}.`
                : detail.message || 'The donor page is not ready to generate yet.';
        }
        if (detail.error === 'invalid_draft_json' || detail.error === 'draft_content_incomplete') {
            return detail.message || 'The draft was incomplete. Please try generating again.';
        }
        return err?.message || 'Generation failed. Please try again.';
    }

    copyLink() {
        navigator.clipboard.writeText(this.micrositeUrl).then(() => {
            const btn = document.getElementById('copyLinkBtn');
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = 'Copy Link'; }, 2000);
        });
    }

    async unpublish() {
        const ok = window.confirm('Unpublish this donor page? The public link will stop working.');
        if (!ok) return;
        const btn = document.getElementById('unpublishBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Unpublishing...';
        }
        try {
            await conversationAPI.unpublishMicrosite();
            ui.showUnpublished();
            ui.setStatus('The donor page is no longer public.');
        } catch (err) {
            console.error(err);
            ui.setStatus('Unpublish failed. Please try again.');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Unpublish Page';
            }
        }
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
