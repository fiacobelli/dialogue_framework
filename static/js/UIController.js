/**
 * UIController - Handles all DOM updates and visual feedback
 * Single source of truth for UI state
 */

class UIController {
    constructor() {
        this.elements = {};
        this.currentPhase = null;
        this.phases = ['WELCOME', 'INTRO', 'RAPPORT', 'BEFORE', 'DURING', 'HOPE', 'PHOTOS'];
    }

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

    // Message display
    showMessage(text) {
        this.elements.messageBubble.textContent = text;
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

    // Phase indicators
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
        }
    }

    // Photo handling
    showPhotoSlot(index, url) {
        const slot = document.getElementById('photo' + index);
        if (slot) slot.innerHTML = `<img src="${url}">`;
    }

    showGenerateSection() {
        this.elements.generateSection.style.display = 'block';
    }

    // Microsite preview
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

        const fullUrl = window.location.origin + data.microsite_url;
        document.getElementById('micrositeUrl').textContent = fullUrl;
        document.getElementById('viewBtn').href = data.microsite_url;
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
}

// Singleton instance
const ui = new UIController();
