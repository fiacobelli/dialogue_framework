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
            status: document.getElementById('status')
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
        this.elements.micHint.textContent = 'Speak when ready';
    }

    showListening() {
        this.elements.micBtn.classList.add('listening');
        this.elements.micBtn.classList.remove('disabled');
        this.elements.micHint.textContent = 'Listening...';
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

    /** Show screening report with classified concerns. */
    showReport(data) {
        document.getElementById('swConcerns').textContent = data.social_worker || '';
        document.getElementById('dietConcerns').textContent = data.dietitian || '';
        document.getElementById('nephConcerns').textContent = data.nephrologist || '';
        document.getElementById('nurseConcerns').textContent = data.nurse_practitioner || '';
        document.getElementById('reportSection').style.display = 'block';
    }
}

// Singleton instance
const ui = new UIController();
