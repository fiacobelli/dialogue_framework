/**
 * ConversationAPI - Handles all backend communication
 * Clean separation of network logic from UI
 */

class ConversationAPI {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
        this.sessionId = null;
    }

    /** Start new session and get opening prompt. */
    async startSession(lang, avatarId) {
        const res = await fetch(`${this.baseUrl}/api/session?lang=${lang}&avatar=${avatarId}`);
        if (!res.ok) throw new Error('Failed to start session');

        const data = await res.json();
        this.sessionId = data.session_id;
        return {
            sessionId: data.session_id,
            phase: data.phase,
            prompt: data.prompt
        };
    }

    /** Send user message and get response. */
    async sendMessage(text) {
        if (!this.sessionId) throw new Error('No active session');

        const res = await fetch(`${this.baseUrl}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: this.sessionId,
                input: text
            })
        });

        if (!res.ok) throw new Error('Failed to send message');
        return await res.json();
    }

    /** Upload photo file to server. */
    async uploadPhoto(file) {
        if (!this.sessionId) throw new Error('No active session');

        const formData = new FormData();
        formData.append('session_id', this.sessionId);
        formData.append('photo', file);

        const res = await fetch(`${this.baseUrl}/api/upload`, {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to upload photo');
        return data;
    }

    /** Generate microsite from conversation. */
    async generateMicrosite(name) {
        if (!this.sessionId) throw new Error('No active session');

        const res = await fetch(`${this.baseUrl}/api/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: this.sessionId,
                name: name
            })
        });

        if (!res.ok) throw new Error('Failed to generate microsite');
        return await res.json();
    }

    async getQRCode() {
        if (!this.sessionId) throw new Error('No active session');
        const res = await fetch(`${this.baseUrl}/api/qr/${this.sessionId}`);
        if (!res.ok) throw new Error('Failed to get QR code');
        return await res.json();
    }

    async getPhotoStatus() {
        if (!this.sessionId) throw new Error('No active session');
        const res = await fetch(`${this.baseUrl}/api/photos/${this.sessionId}`);
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
