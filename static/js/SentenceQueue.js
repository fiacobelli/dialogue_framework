/**
 * SentenceQueue - Chains TTS sentences from an SSE stream without gaps or race conditions.
 *
 * Problem it solves: the SSE stream finishes before the last sentence is spoken,
 * or a sentence finishes speaking while the stream hasn't delivered the next one yet.
 *
 * Usage:
 *   sentenceQueue.configure(onPlay, onFinished);
 *   sentenceQueue.enqueue("Hello there.");   // from SSE onSentence
 *   sentenceQueue.markDone();               // from SSE onDone
 *   // App calls sentenceQueue.onSentenceEnd() after each speak() resolves.
 */
class SentenceQueue {
    constructor() {
        this._queue = [];
        this._streamDone = false;
        this._playing = false;
        this._onPlay = null;
        this._onFinished = null;
    }

    /** Wire up callbacks. Must be called once before any enqueue()/markDone(). */
    configure(onPlay, onFinished) {
        this._onPlay = onPlay;
        this._onFinished = onFinished;
    }

    /** Add a sentence. Plays immediately if nothing is playing; queues otherwise. */
    enqueue(text) {
        if (this._streamDone) return;
        if (this._playing) {
            this._queue.push(text);
        } else {
            this._playing = true;
            this._onPlay(text);
        }
    }

    /**
     * Call this after each speak() resolves (one sentence finished).
     * Dequeues the next sentence, or fires _onFinished if stream is done and queue is empty.
     */
    onSentenceEnd() {
        if (this._queue.length > 0) {
            const next = this._queue.shift();
            this._onPlay(next);
        } else if (this._streamDone) {
            this._playing = false;
            this._onFinished();
        } else {
            this._playing = false;
            // Stream not done yet — enqueue() will restart when next sentence arrives.
        }
    }

    /**
     * Signal that no more sentences are coming from the SSE stream.
     * If nothing is playing and queue is empty, fires _onFinished immediately.
     */
    markDone() {
        this._streamDone = true;
        if (!this._playing && this._queue.length === 0) {
            this._onFinished();
        }
    }

    /** Reset for next turn. */
    reset() {
        this._queue = [];
        this._streamDone = false;
        this._playing = false;
    }
}
