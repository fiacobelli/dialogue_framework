/**
 * TurnFinalizer - Pure policy/timer object for deciding when captured speech
 * should be committed. It does not own VAD, audio buffers, network calls, UI,
 * or the coarse TurnManager state.
 */

const TurnFinalizerState = {
    IDLE: 'idle',
    WAITING_FOR_SPEECH: 'waiting_for_speech',
    CAPTURING: 'capturing',
    POST_SPEECH_PAUSE: 'post_speech_pause',
    COMMITTED: 'committed',
    ABORTED: 'aborted'
};

class TurnFinalizer {
    constructor(callbacks = {}, config = {}) {
        this.callbacks = callbacks;
        this.config = {
            idlePromptMs: config.idlePromptMs ?? TURN_IDLE_PROMPT_MS,
            postSpeechGraceMs: config.postSpeechGraceMs ?? TURN_POST_SPEECH_GRACE_MS,
            extendedPostSpeechGraceMs: config.extendedPostSpeechGraceMs ?? TURN_EXTENDED_POST_SPEECH_GRACE_MS,
            maxSpeechAudioMs: config.maxSpeechAudioMs ?? TURN_MAX_SPEECH_AUDIO_MS,
            maxTurnMs: config.maxTurnMs ?? TURN_MAX_TURN_MS,
            now: config.now || (() => performance.now()),
            setTimer: config.setTimer || ((fn, ms) => setTimeout(fn, ms)),
            clearTimer: config.clearTimer || ((id) => clearTimeout(id)),
        };
        this._timers = new Set();
        this.reset();
    }

    reset() {
        this._clearTimers();
        this.state = TurnFinalizerState.IDLE;
        this.startedAt = null;
        this.firstSpeechAt = null;
        this.lastSpeechEndAt = null;
        this.segmentCount = 0;
        this.speechDurationMs = 0;
        this.idlePromptCount = 0;
        this.extendedPauseCount = 0;
    }

    start() {
        this.reset();
        this.state = TurnFinalizerState.WAITING_FOR_SPEECH;
        this.startedAt = this._now();
        this._schedule(this.config.idlePromptMs, () => this._idlePrompt());
        this._scheduleTurnDeadline(() => this.abort('max_turn'));
    }

    speechStart() {
        if (!this._active()) return;
        if (this.firstSpeechAt === null) this.firstSpeechAt = this._now();
        this.state = TurnFinalizerState.CAPTURING;
        this._clearTimers();
        this._scheduleTurnDeadline(() => this.commit('max_turn'));
    }

    speechEnd(audioDurationMs = 0) {
        if (!this._active()) return;
        this.segmentCount += 1;
        this.speechDurationMs += Math.max(0, Math.round(audioDurationMs || 0));
        this.lastSpeechEndAt = this._now();
        this.state = TurnFinalizerState.POST_SPEECH_PAUSE;
        this._clearTimers();

        if (this.speechDurationMs >= this.config.maxSpeechAudioMs) {
            this.commit('max_audio');
            return;
        }

        const delay = this._postSpeechDelayMs();
        if (delay > this.config.postSpeechGraceMs) {
            this.extendedPauseCount += 1;
        }
        this._schedule(Math.min(this.config.postSpeechGraceMs, delay), () => this._postSpeechPrompt());
        this._schedule(delay, () => this.commit(delay > this.config.postSpeechGraceMs ? 'extended_pause_elapsed' : 'pause_elapsed'));
        this._scheduleTurnDeadline(() => this.commit('max_turn'));
    }

    commit(reason = 'pause_elapsed') {
        if (!this._active()) return false;
        this.state = TurnFinalizerState.COMMITTED;
        this._clearTimers();
        this.callbacks.onCommit?.(this.snapshot(reason));
        return true;
    }

    abort(reason = 'user_cancel') {
        if (!this._active()) return false;
        this.state = TurnFinalizerState.ABORTED;
        this._clearTimers();
        this.callbacks.onAbort?.(this.snapshot(reason));
        return true;
    }

    snapshot(reason = '') {
        const now = this._now();
        return {
            state: this.state,
            reason,
            vad_segment_count: this.segmentCount,
            speech_duration_ms: this.speechDurationMs,
            time_to_first_speech_ms: this.firstSpeechAt === null || this.startedAt === null
                ? null
                : Math.max(0, Math.round(this.firstSpeechAt - this.startedAt)),
            post_speech_pause_ms: this.lastSpeechEndAt === null
                ? null
                : Math.max(0, Math.round(now - this.lastSpeechEndAt)),
            turn_elapsed_ms: this.startedAt === null ? null : Math.max(0, Math.round(now - this.startedAt)),
            idle_prompt_count: this.idlePromptCount,
            extended_pause_count: this.extendedPauseCount,
        };
    }

    _idlePrompt() {
        if (this.state !== TurnFinalizerState.WAITING_FOR_SPEECH) return;
        this.idlePromptCount += 1;
        this.callbacks.onIdlePrompt?.(this.snapshot('idle_prompt'));
        this._schedule(this.config.idlePromptMs, () => this._idlePrompt());
    }

    _postSpeechPrompt() {
        if (this.state !== TurnFinalizerState.POST_SPEECH_PAUSE) return;
        this.callbacks.onPostSpeechPrompt?.(this.snapshot('post_speech_grace_elapsed'));
    }

    _postSpeechDelayMs() {
        const shouldExtend = this.segmentCount >= 2 || this.speechDurationMs < 1800;
        return shouldExtend ? this.config.extendedPostSpeechGraceMs : this.config.postSpeechGraceMs;
    }

    _active() {
        return [
            TurnFinalizerState.WAITING_FOR_SPEECH,
            TurnFinalizerState.CAPTURING,
            TurnFinalizerState.POST_SPEECH_PAUSE,
        ].includes(this.state);
    }

    _schedule(ms, fn) {
        const timer = this.config.setTimer(() => {
            this._timers.delete(timer);
            fn();
        }, ms);
        this._timers.add(timer);
        return timer;
    }

    _scheduleTurnDeadline(fn) {
        if (this.startedAt === null) return null;
        const elapsed = this._now() - this.startedAt;
        return this._schedule(Math.max(0, this.config.maxTurnMs - elapsed), fn);
    }

    _clearTimers() {
        if (!this._timers) {
            this._timers = new Set();
            return;
        }
        this._timers.forEach(timer => this.config.clearTimer(timer));
        this._timers.clear();
    }

    _now() {
        return this.config.now();
    }
}
