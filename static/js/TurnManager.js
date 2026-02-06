/**
 * TurnManager - Handles conversational turn-taking state machine.
 * Ensures only one party (user or system) speaks at a time.
 * States: IDLE -> USER_SPEAKING -> PROCESSING -> SYSTEM_SPEAKING -> IDLE
 */

const TurnState = {
    IDLE: 'idle',
    USER_SPEAKING: 'user_speaking',
    PROCESSING: 'processing',
    SYSTEM_SPEAKING: 'system_speaking'
};

class TurnManager {
    constructor() {
        this.state = TurnState.IDLE;
        this.listeners = {};
    }

    getState() {
        return this.state;
    }

    canUserSpeak() {
        return this.state === TurnState.IDLE;
    }

    canSystemSpeak() {
        return this.state === TurnState.PROCESSING || this.state === TurnState.IDLE;
    }

    canProcess() {
        return this.state === TurnState.USER_SPEAKING;
    }

    // State transitions
    startUserTurn() {
        if (!this.canUserSpeak()) {
            console.warn('Cannot start user turn from state:', this.state);
            return false;
        }
        this._transition(TurnState.USER_SPEAKING);
        return true;
    }

    endUserTurn() {
        if (this.state !== TurnState.USER_SPEAKING) return false;
        this._transition(TurnState.PROCESSING);
        return true;
    }

    startSystemTurn() {
        if (!this.canSystemSpeak()) {
            console.warn('Cannot start system turn from state:', this.state);
            return false;
        }
        this._transition(TurnState.SYSTEM_SPEAKING);
        return true;
    }

    endSystemTurn() {
        if (this.state !== TurnState.SYSTEM_SPEAKING) return false;
        this._transition(TurnState.IDLE);
        return true;
    }

    // For error recovery
    reset() {
        this._transition(TurnState.IDLE);
    }

    // Event system
    on(event, callback) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(callback);
    }

    off(event, callback) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }

    _transition(newState) {
        const oldState = this.state;
        this.state = newState;
        this._emit('stateChange', { from: oldState, to: newState });
        this._emit(newState, { from: oldState });
    }

    _emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(cb => cb(data));
        }
    }
}

// Singleton instance
const turnManager = new TurnManager();
