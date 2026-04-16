/**
 * UIController - Handles all DOM updates and visual feedback
 * Single source of truth for UI state
 */

class UIController {
    constructor() {
        this.elements = {};
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
            progressWrap: document.getElementById('progress-bar-wrap'),
            progressFill: document.getElementById('progress-bar-fill'),
            repeatBtn: document.getElementById('repeatBtn'),
            avatarFrame: document.getElementById('avatarFrame'),
            waveform: document.getElementById('waveform'),
        };
    }

    showConversation() {
        // Layout is always visible in the new design; kept for API compatibility.
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
        this.elements.micHint.textContent = 'Speak when ready';
        this.elements.avatarFrame?.classList.remove('speaking');
        this.elements.waveform?.classList.add('hidden');
    }

    showListening() {
        this.elements.micBtn.classList.add('listening');
        this.elements.micBtn.classList.remove('disabled');
        this.elements.micHint.textContent = 'Listening...';
        this.elements.avatarFrame?.classList.remove('speaking');
        this.elements.waveform?.classList.add('hidden');
    }

    showProcessing() {
        this.elements.micBtn.classList.remove('listening');
        this.elements.micBtn.classList.add('disabled');
        this.elements.micHint.textContent = 'Processing...';
        this.elements.avatarFrame?.classList.remove('speaking');
        this.elements.waveform?.classList.add('hidden');
        this.setStatus('Thinking...');
    }

    showSpeaking() {
        this.elements.micBtn.classList.add('disabled');
        this.elements.micBtn.classList.remove('listening');
        this.elements.micHint.textContent = 'Assistant is speaking...';
        this.elements.avatarFrame?.classList.add('speaking');
        this.elements.waveform?.classList.remove('hidden');
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

    /** Update progress bar. turns = user turns completed, max = MAX_USER_TURNS. */
    showProgress(turns, max) {
        const pct = Math.min(100, Math.round((turns / max) * 100));
        this.elements.progressFill.style.width = pct + '%';
        this.elements.progressWrap.classList.remove('hidden');
    }

    hideProgress() {
        this.elements.progressWrap.classList.add('hidden');
    }

    /** Show repeat button. Caller must verify _lastSpokenText exists before calling. */
    showRepeatButton() {
        this.elements.repeatBtn.style.display = 'inline-block';
    }

    hideRepeatButton() {
        this.elements.repeatBtn.style.display = 'none';
    }

    /** Show thank-you end screen. Report data goes to DB only — not shown to patient. */
    showThankYou() {
        document.getElementById('conversationUI').style.display = 'none';
        document.getElementById('thankYouScreen').style.display = 'flex';
    }
}

// Singleton instance
const ui = new UIController();
