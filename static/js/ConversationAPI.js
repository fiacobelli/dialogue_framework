/**
 * ConversationAPI - Handles all backend communication
 * Clean separation of network logic from UI
 */

class ConversationAPI {
    constructor(baseUrl = window.APP_BASE_PATH || '') {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.sessionId = null;
    }

    _url(path) {
        const normalizedPath = path.startsWith('/') ? path : `/${path}`;
        return `${this.baseUrl}${normalizedPath}`;
    }

    /** Start new session and get opening prompt. */
    async startSession(lang, avatarId) {
        const params = new URLSearchParams({ lang, avatar: avatarId });
        const res = await fetch(this._url(`/api/session?${params.toString()}`));
        if (!res.ok) throw new Error('Failed to start session');

        const data = await res.json();
        this.sessionId = data.session_id;
        return {
            sessionId: data.session_id,
            phase: data.phase,
            prompt: data.prompt,
            progress: data.progress
        };
    }

    /** Send user message and get response. */
    async sendMessage(text, metadata = {}) {
        if (!this.sessionId) throw new Error('No active session');

        const res = await fetch(this._url('/api/chat'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: this.sessionId,
                input: text,
                ...metadata
            })
        });

        if (!res.ok) throw new Error('Failed to send message');
        return await res.json();
    }

    /** Tell the backend the browser could not capture speech for this turn. */
    async sendNoResponse(metadata = {}) {
        return this.sendMessage('', { ...metadata, no_response: true });
    }

    /** Upload photo file to server. */
    async uploadPhoto(file, source = 'desktop') {
        if (!this.sessionId) throw new Error('No active session');

        const formData = new FormData();
        formData.append('session_id', this.sessionId);
        formData.append('photo', file);
        formData.append('source', source);

        const res = await fetch(this._url('/api/upload'), {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to upload photo');
        return data;
    }

    /** Generate microsite from conversation. */
    async generateMicrosite(name, options = {}) {
        if (!this.sessionId) throw new Error('No active session');

        const res = await fetch(this._url('/api/generate'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: this.sessionId,
                name: name,
                allow_partial_photos: Boolean(options.allowPartialPhotos)
            })
        });

        if (!res.ok) {
            let detail = {};
            try {
                detail = await res.json();
            } catch (_) {}
            const err = new Error(detail.message || 'Failed to generate microsite');
            err.status = res.status;
            err.detail = detail;
            throw err;
        }
        return await res.json();
    }

    /** Publish a reviewed donor-page draft. */
    async publishMicrosite(edits, publicationConsent = {}) {
        if (!this.sessionId) throw new Error('No active session');

        const res = await fetch(this._url('/api/publish'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: this.sessionId,
                edits: edits || {},
                publication_consent: publicationConsent || {}
            })
        });

        if (!res.ok) {
            let detail = {};
            try {
                detail = await res.json();
            } catch (_) {}
            const err = new Error(detail.message || 'Failed to publish microsite');
            err.status = res.status;
            err.detail = detail;
            throw err;
        }
        return await res.json();
    }

    async getQRCode() {
        if (!this.sessionId) throw new Error('No active session');
        const res = await fetch(this._url(`/api/qr/${this.sessionId}`));
        if (!res.ok) throw new Error('Failed to get QR code');
        return await res.json();
    }

    async getPhotoStatus() {
        if (!this.sessionId) throw new Error('No active session');
        const res = await fetch(this._url(`/api/photos/${this.sessionId}`));
        if (!res.ok) throw new Error('Failed to get photo status');
        return await res.json();
    }

    getSessionId() {
        return this.sessionId;
    }

    clearSession() {
        this.sessionId = null;
    }
}

// Singleton instance
const conversationAPI = new ConversationAPI();
