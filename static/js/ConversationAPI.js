/**
 * ConversationAPI - Handles all backend communication
 * Clean separation of network logic from UI
 */

class ConversationAPI {
    constructor(baseUrl = window.APP_BASE_PATH || '') {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.sessionId = null;
        this.patientToken = null;
        this.uploadToken = null;
    }

    _url(path) {
        const normalizedPath = path.startsWith('/') ? path : `/${path}`;
        return `${this.baseUrl}${normalizedPath}`;
    }

    _authPayload(extra = {}) {
        return {
            session_id: this.sessionId,
            patient_token: this.patientToken,
            ...extra
        };
    }

    _authQuery(path) {
        const separator = path.includes('?') ? '&' : '?';
        return `${path}${separator}patient_token=${encodeURIComponent(this.patientToken || '')}`;
    }

    /** Start new session and get opening prompt. */
    async startSession(lang, avatarId) {
        const params = new URLSearchParams({ lang, avatar: avatarId });
        const res = await fetch(this._url(`/api/session?${params.toString()}`));
        if (!res.ok) throw new Error('Failed to start session');

        const data = await res.json();
        this.sessionId = data.session_id;
        this.patientToken = data.patient_token || null;
        return {
            sessionId: data.session_id,
            patientToken: data.patient_token,
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
            body: JSON.stringify(this._authPayload({
                input: text,
                ...metadata
            }))
        });

        if (!res.ok) throw new Error('Failed to send message');
        return await res.json();
    }

    /** Persist client-side diagnostics that are not part of a user answer turn. */
    async sendClientEvents(events = []) {
        if (!this.sessionId) throw new Error('No active session');
        if (!events.length) return { status: 'skipped' };

        const res = await fetch(this._url('/api/client-events'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this._authPayload({
                events
            }))
        });

        if (!res.ok) throw new Error('Failed to save client diagnostics');
        return await res.json();
    }

    /** Upload photo file to server. */
    async uploadPhoto(file, source = 'desktop', options = {}) {
        if (!this.sessionId) throw new Error('No active session');

        const formData = new FormData();
        formData.append('session_id', this.sessionId);
        formData.append('patient_token', this.patientToken || '');
        if (this.uploadToken) {
            formData.append('upload_token', this.uploadToken);
        }
        formData.append('photo', file);
        formData.append('source', source);
        if (options.replaceFilename) {
            formData.append('replace_filename', options.replaceFilename);
        }

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
            body: JSON.stringify(this._authPayload({
                name: name,
                allow_partial_photos: Boolean(options.allowPartialPhotos)
            }))
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
            body: JSON.stringify(this._authPayload({
                edits: edits || {},
                publication_consent: publicationConsent || {}
            }))
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

    async unpublishMicrosite(reason = 'user_request') {
        if (!this.sessionId) throw new Error('No active session');

        const res = await fetch(this._url('/api/unpublish'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this._authPayload({
                reason
            }))
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.message || data.error || 'Failed to unpublish microsite');
        return data;
    }

    async deleteMicrosite(reason = 'user_request') {
        if (!this.sessionId) throw new Error('No active session');

        const res = await fetch(this._url('/api/delete'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this._authPayload({
                reason
            }))
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.message || data.error || 'Failed to delete microsite');
        return data;
    }

    async getQRCode() {
        if (!this.sessionId) throw new Error('No active session');
        const res = await fetch(this._url(this._authQuery(`/api/qr/${this.sessionId}`)));
        if (!res.ok) throw new Error('Failed to get QR code');
        const data = await res.json();
        this.uploadToken = data.upload_token || null;
        return data;
    }

    async getPhotoStatus() {
        if (!this.sessionId) throw new Error('No active session');
        const res = await fetch(this._url(this._authQuery(`/api/photos/${this.sessionId}`)));
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to get photo status');
        return data;
    }

    async updatePhotoMetadata(photos = []) {
        if (!this.sessionId) throw new Error('No active session');
        const res = await fetch(this._url(`/api/photos/${this.sessionId}/metadata`), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this._authPayload({ photos }))
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to update photo details');
        return data;
    }

    getSessionId() {
        return this.sessionId;
    }

    getPatientToken() {
        return this.patientToken;
    }

    clearSession() {
        this.sessionId = null;
        this.patientToken = null;
        this.uploadToken = null;
    }
}

// Singleton instance
const conversationAPI = new ConversationAPI();
