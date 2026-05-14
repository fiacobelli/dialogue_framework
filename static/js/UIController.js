/**
 * UIController - Handles all DOM updates and visual feedback
 * Single source of truth for UI state
 */

class UIController {
    constructor() {
        this.elements = {};
        this.currentPhase = null;
        this.phases = ['WELCOME', 'INTRO', 'RAPPORT', 'BEFORE', 'DURING', 'HOPE', 'PHOTOS'];
        this.wordRevealInterval = null;
        this.pendingWords = [];
        this.currentWordIndex = 0;
    }

    /** Initialize DOM element references. */
    init() {
        this.elements = {
            conversationScreen: document.getElementById('conversation-screen'),
            messageBubble: document.getElementById('messageBubble'),
            micBtn: document.getElementById('micBtn'),
            micHint: document.getElementById('micHint'),
            input: document.getElementById('input'),
            status: document.getElementById('status'),
            photoSection: document.getElementById('photoSection'),
            generateSection: document.getElementById('generateSection'),
            micrositePreview: document.getElementById('micrositePreview')
        };
    }

    showConversation() {
        this.elements.conversationScreen.style.display = 'block';
    }

    /** Display message in the avatar speech bubble. */
    showMessage(text) {
        this.elements.messageBubble.textContent = text;
    }

    /** Display message word-by-word synchronized with speech. */
    showMessageAnimated(text, wordsPerMinute = 150) {
        this.stopMessageAnimation();

        this.pendingWords = text.split(/\s+/);
        this.currentWordIndex = 0;
        const msPerWord = Math.round(60000 / wordsPerMinute);

        this.elements.messageBubble.textContent = '';

        this.wordRevealInterval = setInterval(() => {
            if (this.currentWordIndex < this.pendingWords.length) {
                const visibleText = this.pendingWords.slice(0, this.currentWordIndex + 1).join(' ');
                this.elements.messageBubble.textContent = visibleText;
                this.currentWordIndex++;
            } else {
                this.stopMessageAnimation();
            }
        }, msPerWord);
    }

    /** Stop animation and show all remaining text. */
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

    setStatus(msg) {
        this.elements.status.textContent = msg;
    }

    // Turn state visuals
    showIdle() {
        this.elements.micBtn.classList.remove('listening', 'disabled');
        this.elements.micHint.textContent = 'Tap to speak';
    }

    showListening() {
        this.elements.micBtn.classList.add('listening');
        this.elements.micBtn.classList.remove('disabled');
        this.elements.micHint.textContent = 'Listening... tap when done';
    }

    showProcessing() {
        this.elements.micBtn.classList.remove('listening');
        this.elements.micBtn.classList.add('disabled');
        this.elements.micHint.textContent = 'Processing...';
        this.setStatus('Thinking...');
    }

    showSpeaking() {
        this.elements.micBtn.classList.add('disabled');
        this.elements.micBtn.classList.remove('listening');
        this.elements.micHint.textContent = 'Assistant is speaking...';
    }

    // Transcript display
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

    /** Update phase indicator dots. */
    updatePhase(phase) {
        this.currentPhase = phase;
        document.querySelectorAll('.dot').forEach(el => el.classList.remove('active', 'done'));

        const idx = this.phases.indexOf(phase);
        for (let i = 0; i < idx; i++) {
            const dot = document.getElementById('dot-' + this.phases[i].toLowerCase());
            if (dot) dot.classList.add('done');
        }
        const activeDot = document.getElementById('dot-' + phase.toLowerCase());
        if (activeDot) activeDot.classList.add('active');

        if (phase === 'PHOTOS' || phase === 'COMPLETE') {
            this.elements.photoSection.classList.add('visible');
            this.showQRSection();
        }
    }

    // QR code display
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

    updatePhotoProgress(count, max) {
        const el = document.getElementById('photoProgress');
        if (el) el.textContent = `${count}/${max} photos uploaded`;
    }

    // Photo handling
    showPhotoSlot(index, url) {
        const slot = document.getElementById('photo' + index);
        if (slot) slot.innerHTML = `<img src="${url}">`;
    }

    showGenerateSection() {
        this.elements.generateSection.style.display = 'block';
    }

    showGenerating() {
        this.elements.generateSection.style.display = 'block';
        const btn = document.getElementById('generateBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Creating your donor page...';
        }
    }

    /** Render microsite preview with share buttons. */
    showMicrositePreview(data) {
        document.getElementById('siteName').textContent = data.name + "'s Story";

        const content = data.my_story
            ? `<strong>My Story:</strong> ${data.my_story}<br><br>
               <strong>Living with Kidney Disease:</strong> ${data.my_struggle}<br><br>
               <strong>Why I Need Your Help:</strong> ${data.my_hope}`
            : data.content;

        document.getElementById('siteContent').innerHTML = content;
        document.getElementById('sitePhotos').innerHTML = data.photos
            .map(p => `<div class="photo-slot"><img src="${p}"></div>`)
            .join('');

        const fullUrl = data.microsite_absolute_url || absoluteAppUrl(data.microsite_url);
        document.getElementById('micrositeUrl').innerHTML = `<a href="${fullUrl}" target="_blank">${fullUrl}</a>`;
        document.getElementById('viewBtn').href = fullUrl;
        document.getElementById('shareFb').href =
            'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(fullUrl);
        document.getElementById('shareWa').href =
            'https://wa.me/?text=' + encodeURIComponent(data.name + "'s Story: " + fullUrl);
        document.getElementById('shareEmail').href =
            'mailto:?subject=' + encodeURIComponent(data.name + "'s Story") +
            '&body=' + encodeURIComponent(fullUrl);

        this.elements.micrositePreview.classList.add('visible');
        return fullUrl;
    }

    /** Show celebration section with CTA button. */
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

// Singleton instance
const ui = new UIController();
