/**
 * ConversationAPI - Handles all backend communication
 * Clean separation of network logic from UI
 */

class ConversationAPI {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
        this.sessionId = null;
    }

    /** Start new session and get opening prompt. Captures screen dimensions for research. */
    async startSession(lang, avatarId, patientId) {
        const body = { lang, avatar: avatarId, patient_id: patientId };
        // Screen dimensions: logged server-side at DEBUG level for research context
        if (window.screen && window.screen.width) {
            body.screen_width  = window.screen.width;
            body.screen_height = window.screen.height;
        }
        const res = await fetch(`${this.baseUrl}/api/session`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error('Failed to start session');

        const data = await res.json();
        this.sessionId = data.session_id;
        return { sessionId: data.session_id, phase: data.phase, prompt: data.prompt };
    }

    /**
     * Send user message and get response.
     * meta: optional instrumentation fields — input_modality, response_latency_ms,
     *       speech_confidence, client_sent_at, no_response, events.
     */
    async sendMessage(text, meta = {}) {
        if (!this.sessionId) throw new Error('No active session');

        const res = await fetch(`${this.baseUrl}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: this.sessionId, input: text, ...meta })
        });

        if (!res.ok) throw new Error('Failed to send message');
        return await res.json();
    }

    /**
     * Stream LLM response via SSE. Calls onSentence for each sentence, onDone when finished.
     * Returns after the HTTP stream is fully consumed; TTS may still be in progress.
     */
    async sendMessageStream(text, meta, { onSentence, onDone, onError }) {
        if (!this.sessionId) { onError('No active session'); return; }

        let response;
        try {
            response = await fetch(`${this.baseUrl}/api/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.sessionId, input: text, ...meta })
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
        } catch (err) {
            onError(err.message);
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let partial = '';
        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                partial += decoder.decode(value, { stream: true });
                const lines = partial.split('\n');
                partial = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const raw = line.slice(6).trim();
                    if (!raw) continue;
                    try {
                        const event = JSON.parse(raw);
                        if (event.type === 'sentence') onSentence(event.text);
                        else if (event.type === 'done')  onDone(event);
                        else if (event.type === 'error') onError(event.message);
                    } catch (_) { /* malformed JSON chunk — skip */ }
                }
            }
        } catch (err) {
            onError(err.message);
        }
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

    getSessionId() { return this.sessionId; }
    clearSession()  { this.sessionId = null; }
}

// Singleton instance
const conversationAPI = new ConversationAPI();
