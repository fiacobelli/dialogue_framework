/**
 * InputHandler - Sets up all DOM-level event listeners.
 * Extracted from App.js to keep App under the 200-line limit.
 * Calls back into App via the injected app reference.
 */
class InputHandler {
    constructor(app) {
        this._app = app;
    }

    /** Wire up the patient ID form (last name + DOB) and Begin button. */
    setupBeginOverlay() {
        const lastNameInput = document.getElementById('lastNameInput');
        const dobInput      = document.getElementById('dobInput');
        const beginBtn      = document.getElementById('beginBtn');
        const hint          = document.getElementById('pinHint');
        document.getElementById('micBtn')?.classList.add('hidden');

        const sanitizeName = (v) => v.trim().toLowerCase().replace(/[^a-z]/g, '');
        const extractDigits = (v) => v.replace(/\D/g, '').slice(0, 8);
        const formatDob = (d) => {
            const mm = d.slice(0, 2), dd = d.slice(2, 4), yyyy = d.slice(4, 8);
            return [mm, dd, yyyy].filter(Boolean).join('/');
        };
        const buildId = () =>
            `${sanitizeName(lastNameInput.value)}-${extractDigits(dobInput.value)}`;

        const validate = () => {
            const name = sanitizeName(lastNameInput.value);
            const dob  = extractDigits(dobInput.value);
            dobInput.value = formatDob(dob);
            const ok = name.length >= 2 && dob.length === 8;
            beginBtn.disabled = !ok;
            hint.textContent = name.length < 2 ? 'Enter at least two letters for your last name'
                : dob.length < 8 ? 'Enter date of birth as MM/DD/YYYY' : '';
            return ok;
        };

        lastNameInput.addEventListener('input', validate);
        dobInput.addEventListener('input', (e) => {
            e.target.value = formatDob(extractDigits(e.target.value));
            validate();
        });
        beginBtn.addEventListener('click', () => {
            if (validate()) this._app._beginScreeningWithPin(buildId());
        });
    }

    /** Wire up mic button, text input, send button, and repeat button. */
    setupUIEvents() {
        document.getElementById('micBtn')
            .addEventListener('click', () => this._app.toggleMic());

        const input = document.getElementById('input');
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this._app.sendTextInput();
        });

        const sendBtn = document.getElementById('sendBtn');
        if (sendBtn) sendBtn.addEventListener('click', () => this._app.sendTextInput());

        const repeatBtn = document.getElementById('repeatBtn');
        if (repeatBtn) repeatBtn.addEventListener('click', () => this._app.repeatLastMessage());
    }
}
