/**
 * UIController - Handles all DOM updates and visual feedback.
 */

class UIController {
    constructor() {
        this.elements = {};
        this.wordRevealInterval = null;
        this.pendingWords = [];
        this.currentWordIndex = 0;
        this.currentDraftData = null;
    }

    init() {
        this.elements = {
            conversationScreen: document.getElementById('conversation-screen'),
            avatarPanel: document.querySelector('.avatar-panel'),
            interactionPanel: document.querySelector('.interaction-panel'),
            hubBackBtn: document.getElementById('hubBackBtn'),
            beginOverlay: document.getElementById('beginOverlay'),
            beginBtn: document.getElementById('beginBtn'),
            micPreflightStatus: document.getElementById('micPreflightStatus'),
            conversationUI: document.getElementById('conversationUI'),
            messageBubble: document.getElementById('messageBubble'),
            micBtn: document.getElementById('micBtn'),
            micHint: document.getElementById('micHint'),
            input: document.getElementById('input'),
            status: document.getElementById('status'),
            photoSection: document.getElementById('photoSection'),
            photoStatus: document.getElementById('photoStatus'),
            generateSection: document.getElementById('generateSection'),
            reviewSection: document.getElementById('reviewSection'),
            heroPhotoPicker: document.getElementById('heroPhotoPicker'),
            micrositePreview: document.getElementById('micrositePreview'),
            repeatBtn: document.getElementById('repeatBtn'),
            skipQuestionBtn: document.getElementById('skipQuestionBtn'),
            avatarFrame: document.getElementById('avatarFrame'),
            waveform: document.getElementById('waveform'),
            progressWrap: document.getElementById('progress-bar-wrap'),
            progressFill: document.getElementById('progress-bar-fill'),
            progressText: document.getElementById('progressText'),
        };
    }

    showBeginOverlay() {
        if (this.elements.beginOverlay) {
            this.elements.beginOverlay.style.display = 'flex';
        }
        this.hideConversation();
    }

    hideBeginOverlay() {
        if (this.elements.beginOverlay) {
            this.elements.beginOverlay.style.display = 'none';
        }
    }

    setBeginLoading(isLoading, label = null) {
        const btn = this.elements.beginBtn;
        if (!btn) return;
        btn.disabled = Boolean(isLoading);
        if (label) {
            btn.textContent = label;
            return;
        }
        btn.textContent = isLoading ? 'Getting Ludi ready...' : 'Begin interview';
    }

    showMicPreflight(status, message, detail = '') {
        const el = this.elements.micPreflightStatus;
        if (!el) return;
        el.className = `mic-preflight ${status || 'info'}`;
        el.innerHTML = '';

        const messageEl = document.createElement('strong');
        messageEl.textContent = message;
        el.appendChild(messageEl);

        if (detail) {
            const detailEl = document.createElement('span');
            detailEl.textContent = detail;
            el.appendChild(detailEl);
        }
    }

    clearMicPreflight() {
        const el = this.elements.micPreflightStatus;
        if (!el) return;
        el.className = 'mic-preflight';
        el.textContent = '';
    }

    showConversation() {
        this.setPostInterviewMode(false);
        this.hideBeginOverlay();
        if (this.elements.conversationUI) {
            this.elements.conversationUI.style.display = 'flex';
        }
    }

    hideConversation() {
        if (this.elements.conversationUI) {
            this.elements.conversationUI.style.display = 'none';
        }
    }

    showMessage(text) {
        this.elements.messageBubble.classList.remove('pulsing');
        this._setMessageLengthClass(text);
        this.elements.messageBubble.textContent = text;
    }

    clearMessage() {
        this.elements.messageBubble.classList.remove('pulsing');
        this.elements.messageBubble.textContent = '';
    }

    appendMessage(text) {
        const current = this.elements.messageBubble.textContent;
        const next = current ? `${current} ${text}` : text;
        this._setMessageLengthClass(next);
        this.elements.messageBubble.textContent = next;
    }

    showMessageAnimated(text, wordsPerMinute = 185) {
        this.stopMessageAnimation();
        this.elements.messageBubble.classList.remove('pulsing');
        this._setMessageLengthClass(text);

        this.pendingWords = text.split(/\s+/);
        this.currentWordIndex = 0;
        const msPerWord = Math.round(60000 / wordsPerMinute);

        this.elements.messageBubble.textContent = '';

        this.wordRevealInterval = setInterval(() => {
            if (this.currentWordIndex < this.pendingWords.length) {
                this.elements.messageBubble.textContent = this.pendingWords
                    .slice(0, this.currentWordIndex + 1)
                    .join(' ');
                this.currentWordIndex++;
            } else {
                this.stopMessageAnimation();
            }
        }, msPerWord);
    }

    stopMessageAnimation() {
        if (this.wordRevealInterval) {
            clearInterval(this.wordRevealInterval);
            this.wordRevealInterval = null;
        }
        if (this.pendingWords.length > 0) {
            this.elements.messageBubble.textContent = this.pendingWords.join(' ');
            this.pendingWords = [];
            this.currentWordIndex = 0;
        }
    }

    _setMessageLengthClass(text) {
        const bubble = this.elements.messageBubble;
        if (!bubble) return;
        const wordCount = String(text || '').trim().split(/\s+/).filter(Boolean).length;
        bubble.classList.toggle('long-message', wordCount > 55);
        bubble.classList.toggle('very-long-message', wordCount > 95);
    }

    setStatus(msg) {
        this.elements.status.textContent = msg;
    }

    showIdle() {
        this.elements.micBtn.classList.remove('listening', 'disabled', 'paused');
        this.elements.micHint.textContent = 'Speak when ready';
        this.elements.avatarFrame?.classList.remove('speaking');
        this.elements.waveform?.classList.add('hidden');
    }

    showListening() {
        this.elements.micBtn.classList.add('listening');
        this.elements.micBtn.classList.remove('disabled', 'paused');
        this.elements.micHint.textContent = 'Listening. Take your time.';
        this.elements.avatarFrame?.classList.remove('speaking');
        this.elements.waveform?.classList.add('hidden');
    }

    showListeningIdle() {
        this.elements.micBtn.classList.add('listening');
        this.elements.micBtn.classList.remove('disabled', 'paused');
        this.elements.micHint.textContent = 'Still listening. Take your time, or type your answer below.';
        this.elements.waveform?.classList.add('hidden');
    }

    showPostSpeechPause() {
        this.elements.micBtn.classList.add('listening');
        this.elements.micBtn.classList.remove('disabled', 'paused');
        this.elements.micHint.textContent = 'I heard you. Keep going if you need a moment.';
        this.elements.waveform?.classList.add('hidden');
    }

    showProcessing() {
        this.elements.micBtn.classList.remove('listening', 'paused');
        this.elements.micBtn.classList.add('disabled');
        this.elements.micHint.textContent = 'Processing...';
        this.elements.avatarFrame?.classList.remove('speaking');
        this.elements.waveform?.classList.add('hidden');
        this.elements.messageBubble?.classList.add('pulsing');
        this.setStatus('');
    }

    showTranscribing() {
        this.elements.micBtn.classList.remove('listening', 'paused');
        this.elements.micBtn.classList.add('disabled');
        this.elements.micHint.textContent = 'Processing what you said...';
        this.elements.avatarFrame?.classList.remove('speaking');
        this.elements.waveform?.classList.add('hidden');
        this.elements.messageBubble?.classList.add('pulsing');
        this.setStatus('Processing what you said...');
    }

    showSpeaking() {
        this.elements.micBtn.classList.remove('listening', 'disabled', 'paused');
        this.elements.micHint.textContent = 'Tap to pause';
        this.elements.avatarFrame?.classList.add('speaking');
        this.elements.waveform?.classList.remove('hidden');
    }

    showPaused() {
        this.elements.micBtn.classList.add('paused');
        this.elements.micBtn.classList.remove('listening', 'disabled');
        this.elements.micHint.textContent = 'Tap mic to resume';
        this.elements.waveform?.classList.add('hidden');
    }

    showResumed() {
        this.elements.micBtn.classList.remove('paused');
        this.elements.micHint.textContent = 'Speak when ready';
    }

    showTranscript(text, isInterim = false) {
        this.elements.input.value = text;
        if (isInterim) {
            this.elements.input.classList.add('interim');
        } else {
            this.elements.input.classList.remove('interim');
        }
    }

    clearTranscript() {
        this.elements.input.value = '';
        this.elements.input.classList.remove('interim');
    }

    showRepeatButton() {
        if (this.elements.repeatBtn) this.elements.repeatBtn.style.display = 'inline-block';
    }

    hideRepeatButton() {
        if (this.elements.repeatBtn) this.elements.repeatBtn.style.display = 'none';
    }

    showProgress(turns, max) {
        if (!this.elements.progressWrap || !this.elements.progressFill) return;
        const pct = Math.min(100, Math.round((turns / max) * 100));
        this.elements.progressFill.style.width = `${pct}%`;
        this.elements.progressWrap.classList.remove('hidden');
    }

    updateProgress(progress) {
        if (!progress || !this.elements.progressWrap || !this.elements.progressFill) return;
        const pct = Math.max(0, Math.min(100, Number(progress.percent || 0)));
        this.elements.progressFill.style.width = `${pct}%`;
        this.elements.progressWrap.classList.remove('hidden');

        if (this.elements.progressText) {
            const current = Number(progress.current_step || 0);
            const total = Number(progress.total_steps || 0);
            const stepText = current > 0 && total > 0 ? `Step ${current} of ${total}` : progress.label;
            this.elements.progressText.textContent = stepText === progress.label
                ? (progress.label || 'Interview')
                : `${progress.label || 'Interview'} · ${stepText}`;
            this.elements.progressText.classList.remove('hidden');
        }

        if (this.elements.skipQuestionBtn) {
            const canSkip = ['STORY', 'FINAL_DETAILS'].includes(progress.phase);
            this.elements.skipQuestionBtn.style.display = canSkip ? 'inline-flex' : 'none';
        }
    }

    hideProgress() {
        this.elements.progressWrap?.classList.add('hidden');
        this.elements.progressText?.classList.add('hidden');
    }

    updatePhase(phase) {
        if (phase === 'PHOTOS' || phase === 'COMPLETE') {
            this.showPhotoFlow();
        }
    }

    setPostInterviewMode(enabled) {
        this.elements.conversationScreen?.classList.toggle('post-interview-mode', Boolean(enabled));
        if (this.elements.hubBackBtn) {
            this.elements.hubBackBtn.style.display = enabled ? 'inline-flex' : 'none';
        }
    }

    showPhotoFlow() {
        this.setPostInterviewMode(true);
        this.hideConversation();
        this.elements.photoSection?.classList.add('visible');
        this.showQRSection();
    }

    showQRSection() {
        const section = document.getElementById('qrSection');
        if (section) section.style.display = 'block';
    }

    setQRCode(qrImage, uploadUrl) {
        const img = document.getElementById('qrCode');
        const link = document.getElementById('uploadLink');
        if (img) img.src = qrImage;
        if (link) {
            link.href = uploadUrl;
            link.textContent = uploadUrl;
        }
    }

    setPhotoStatus(message, type = 'info') {
        const el = this.elements.photoStatus;
        if (!el) return;
        el.textContent = message || '';
        el.className = `photo-status ${type || 'info'}`;
    }

    updatePhotoProgress(count, max) {
        const el = document.getElementById('photoProgress');
        const safeCount = Number(count || 0);
        const safeMax = Number(max || 3);
        if (el) {
            if (safeCount >= safeMax) {
                el.textContent = `${safeMax}/${safeMax} photos received`;
            } else if (safeCount > 0) {
                el.textContent = `${safeCount} of ${safeMax} photos received`;
            } else {
                el.textContent = `Waiting for photos from phone or this device`;
            }
        }
        this.updateContinueWithPhotos(count, max);
    }

    showPhotoSlot(index, photo) {
        const slot = document.getElementById(`photo${index}`);
        if (!slot) return;
        const item = typeof photo === 'string' ? { url: photo, stored_filename: '', photo_role: 'general' } : (photo || {});
        const escapeHtml = (value) => String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
        const filename = escapeHtml(item.stored_filename || '');
        const url = escapeHtml(item.url || '');
        const role = escapeHtml(item.photo_role || 'general');
        const guidance = {
            before: {
                label: 'Who I am',
                description: 'Your life, personality, family, work, school, community, or something meaningful.'
            },
            during: {
                label: 'My kidney journey',
                description: 'Treatment, dialysis, appointments, or daily life with kidney disease.'
            },
            hope: {
                label: 'My hope after transplant',
                description: 'What you hope to return to, do again, or experience with a transplant.'
            },
            general: {
                label: 'Story photo',
                description: 'A photo chosen to help tell this story.'
            }
        };
        const details = guidance[item.photo_role || 'general'] || guidance.general;
        slot.classList.add('filled');
        slot.dataset.filename = item.stored_filename || '';
        slot.dataset.role = item.photo_role || 'general';
        slot.title = 'Photo uploaded. Click to replace this photo.';
        slot.innerHTML = `
            <img src="${url}" alt="Uploaded photo">
            <div class="photo-slot-caption" data-filename="${filename}" data-role="${role}">
                <strong>${escapeHtml(details.label)}</strong>
                <small>${escapeHtml(details.description)}</small>
            </div>
        `;
    }

    showGenerateSection() {
        this.elements.generateSection.style.display = 'block';
        if (this.elements.reviewSection) this.elements.reviewSection.style.display = 'none';
        const btn = document.getElementById('generateBtn');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Preview My Donor Page';
        }
    }

    updateContinueWithPhotos(count, max) {
        const btn = document.getElementById('continueWithPhotosBtn');
        if (!btn) return;
        const hasPartialPhotos = count > 0 && count < max;
        btn.style.display = hasPartialPhotos ? 'block' : 'none';
        btn.disabled = !hasPartialPhotos;
        btn.textContent = hasPartialPhotos
            ? `Continue with ${count} uploaded photo${count === 1 ? '' : 's'}`
            : 'Continue with these photos';
    }

    showGenerating() {
        this.elements.generateSection.style.display = 'block';
        if (this.elements.reviewSection) this.elements.reviewSection.style.display = 'none';
        const btn = document.getElementById('generateBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Preparing your preview...';
        }
    }

    showDraftReview(data) {
        this.currentDraftData = data || {};
        this.setPostInterviewMode(true);
        if (this.elements.photoSection) this.elements.photoSection.classList.remove('visible');
        if (this.elements.generateSection) this.elements.generateSection.style.display = 'none';
        if (this.elements.reviewSection) this.elements.reviewSection.style.display = 'block';

        const fields = {
            reviewName: data.name || '',
            reviewHeadline: data.headline || '',
            reviewShortIntro: data.short_intro || '',
            reviewPersonalIdentity: data.personal_identity || data.my_story || '',
            reviewKidneyJourney: data.kidney_journey || '',
            reviewDailyImpact: data.daily_impact || data.my_struggle || '',
            reviewTransplantHope: data.transplant_hope || data.my_hope || '',
            reviewDonorMessage: data.donor_message || '',
        };
        Object.entries(fields).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.value = value;
        });

        this.showCampaignPreview(data, document.getElementById('draftPreview'), { privatePreview: true });
        this.showHeroPhotoPicker(data);
        const editPanel = document.getElementById('editStoryPanel');
        if (editPanel) editPanel.open = false;
    }

    showHeroPhotoPicker(data) {
        const container = this.elements.heroPhotoPicker || document.getElementById('heroPhotoPicker');
        if (!container) return;

        const photos = (data?.photo_items || []).filter(item => item?.url && item?.stored_filename);
        if (!photos.length) {
            container.innerHTML = '';
            container.hidden = true;
            return;
        }

        const requested = data.hero_photo || photos[0].stored_filename;
        const selected = photos.some(photo => photo.stored_filename === requested)
            ? requested
            : photos[0].stored_filename;
        const escapeHtml = (value) => String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');

        container.hidden = false;
        container.innerHTML = `
            <div class="hero-photo-picker-copy">
                <strong>Choose your main photo</strong>
                <span>This becomes the most prominent photo people see.</span>
            </div>
            <div class="hero-photo-options">
                ${photos.map((photo, index) => `
                    <label class="hero-photo-option${photo.stored_filename === selected ? ' is-selected' : ''}">
                        <input type="radio" name="heroPhoto" value="${escapeHtml(photo.stored_filename)}" ${photo.stored_filename === selected ? 'checked' : ''}>
                        <img src="${escapeHtml(photo.url)}" alt="Photo option ${index + 1}">
                    </label>
                `).join('')}
            </div>
        `;

        container.querySelectorAll('input[name="heroPhoto"]').forEach((input) => {
            input.addEventListener('change', () => {
                container.querySelectorAll('.hero-photo-option').forEach(label => {
                    label.classList.toggle('is-selected', label.contains(input));
                });
                const chosen = photos.find(photo => photo.stored_filename === input.value);
                if (chosen) this.updatePreviewHeroPhoto(chosen.url);
            });
        });
    }

    updatePreviewHeroPhoto(url) {
        const img = document.querySelector('#draftPreview .campaign-profile-photo img');
        if (img && url) img.src = url;
    }

    showCampaignPreview(data, container, options = {}) {
        if (!container) return;
        if (data.preview_html) {
            container.innerHTML = data.preview_html;
            return;
        }
        container.innerHTML = '<p class="preview-error">Preview is unavailable. Please regenerate the page draft.</p>';
    }

    getDraftReviewEdits() {
        return {
            name: document.getElementById('reviewName')?.value.trim() || '',
            headline: document.getElementById('reviewHeadline')?.value.trim() || '',
            short_intro: document.getElementById('reviewShortIntro')?.value.trim() || '',
            personal_identity: document.getElementById('reviewPersonalIdentity')?.value.trim() || '',
            kidney_journey: document.getElementById('reviewKidneyJourney')?.value.trim() || '',
            daily_impact: document.getElementById('reviewDailyImpact')?.value.trim() || '',
            transplant_hope: document.getElementById('reviewTransplantHope')?.value.trim() || '',
            donor_message: document.getElementById('reviewDonorMessage')?.value.trim() || '',
            hero_photo: document.querySelector('input[name="heroPhoto"]:checked')?.value || '',
        };
    }

    getPublicationConsent() {
        return {
            accepted: Boolean(document.getElementById('publicationConsent')?.checked),
            version: 'publication-v1',
        };
    }

    showPublishing() {
        const btn = document.getElementById('publishBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Creating public page...';
        }
        this.setStatus('');
    }

    showPublished() {
        this.setPostInterviewMode(true);
        const btn = document.getElementById('publishBtn');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Approve and Create Public Page';
        }
        if (this.elements.reviewSection) this.elements.reviewSection.style.display = 'none';
    }

    showUnpublished() {
        const btn = document.getElementById('unpublishBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Page Unpublished';
        }
        const viewBtn = document.getElementById('viewBtn');
        if (viewBtn) {
            viewBtn.removeAttribute('href');
            viewBtn.textContent = 'Page Unpublished';
        }
        const cta = document.getElementById('viewPageCTA');
        if (cta) {
            cta.removeAttribute('href');
            cta.textContent = 'Page Unpublished';
        }
    }

    showMicrositePreview(data) {
        document.getElementById('siteName').textContent = `${data.name}'s Story`;

        this.showCampaignPreview(data, document.getElementById('siteContent'));
        document.getElementById('sitePhotos').innerHTML = '';

        const fullUrl = data.microsite_absolute_url || absoluteAppUrl(data.microsite_url);
        document.getElementById('micrositeUrl').innerHTML = `<a href="${fullUrl}" target="_blank">${fullUrl}</a>`;
        document.getElementById('viewBtn').href = fullUrl;
        document.getElementById('shareFb').href =
            `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(fullUrl)}`;
        document.getElementById('shareWa').href =
            `https://wa.me/?text=${encodeURIComponent(`${data.name}'s Story: ${fullUrl}`)}`;
        document.getElementById('shareEmail').href =
            `mailto:?subject=${encodeURIComponent(`${data.name}'s Story`)}` +
            `&body=${encodeURIComponent(fullUrl)}`;

        this.elements.micrositePreview.classList.add('visible');
        return fullUrl;
    }

    showCelebration(micrositeUrl) {
        if (!micrositeUrl) {
            console.error('showCelebration: missing URL');
            return;
        }
        const section = document.getElementById('celebrationSection');
        const btn = document.getElementById('viewPageCTA');
        if (!section || !btn) {
            console.error('showCelebration: elements not found');
            return;
        }
        btn.href = micrositeUrl;
        section.style.display = 'block';
        section.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

const ui = new UIController();

window.copyCampaignLink = function copyCampaignLink(url) {
    const write = navigator.clipboard
        ? navigator.clipboard.writeText(url)
        : Promise.resolve(window.prompt('Copy this link:', url));
    write.then(() => {
        const btn = document.getElementById('copyBtn');
        if (!btn) return;
        btn.textContent = 'Copied';
        setTimeout(() => { btn.textContent = 'Copy Link'; }, 2000);
    });
};
