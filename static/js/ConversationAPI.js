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

    /** Classify screening responses into professional buckets. */
    async classifyResponses() {
        if (!this.sessionId) throw new Error('No active session');

        const res = await fetch(`${this.baseUrl}/api/classify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: this.sessionId })
        });

        if (!res.ok) throw new Error('Failed to classify responses');
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
